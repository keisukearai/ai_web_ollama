"""
qwen2.5-techbridge の回答品質自動テスト

使い方:
  python test_faq_quality.py

前提:
  - Django サーバーが起動済み（http://localhost:8000）または TEST_BASE_URL を指定
  - test_faq_questions.json が同じディレクトリにある

結果は test_results_<timestamp>.json にも保存されます。
"""

import json
import time
import datetime
import requests
import sys
import os
import re
import math

# ── Django 環境セットアップ（DB直接参照用・任意）─────────────────────
_DJANGO_AVAILABLE = False
try:
    _BACKEND_DIR = os.path.join(os.path.dirname(__file__), 'backend')
    sys.path.insert(0, _BACKEND_DIR)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings as django_settings
    from api.models import FAQ
    _DJANGO_AVAILABLE = True
except Exception:
    pass

# ──────────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
SPREADSHEET_ID = "1NOrZGflQbD2DU24VLzGriiW_SfNjXjY5P5kJdn9aVMM"
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "backend/credentials/google_sheets.json")
CHAT_ENDPOINT = f"{BASE_URL}/api/chat/"
MODEL = "qwen2.5-techbridge"
TIMEOUT = 120
EMBED_MODEL = "nomic-embed-text"
FAQ_TOP_K = 5
FAQ_MIN_SIMILARITY = 0.75

QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "test_faq_questions.json")

GLOBAL_NG_PATTERNS = [
    "エラー",
    "Ollama接続エラー",
    "タイムアウト",
]

UNKNOWN_KEYWORDS = [
    "情報がありません",
    "わかりません",
    "お答えできません",
    "対応できません",
    "範囲外",
    "申し訳",
    "持ち合わせていません",
    "ご用意がありません",
    "ございません",
    "該当する情報がありません",
    "見つかりません",
]


def _cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def get_best_faq(question: str) -> tuple[object | None, float]:
    """質問に最もマッチするFAQエントリとスコアを返す。見つからなければ (None, 0.0)"""
    if not _DJANGO_AVAILABLE:
        return None, 0.0
    ollama_url = getattr(django_settings, 'OLLAMA_URL', 'http://localhost:11434')
    try:
        resp = requests.post(
            f"{ollama_url}/api/embed",
            json={'model': EMBED_MODEL, 'input': question},
            timeout=15,
        )
        resp.raise_for_status()
        q_vec = resp.json()['embeddings'][0]
    except Exception as e:
        print(f"  [警告] ベクトル化失敗: {e}")
        return None, 0.0

    # キーワードマッチ優先
    for faq in FAQ.objects.exclude(search_keywords=''):
        for kw in faq.search_keywords.split(','):
            kw = kw.strip()
            if kw and kw in question:
                return faq, 1.0

    # ベクトル検索
    faqs = list(FAQ.objects.exclude(embedding=''))
    best_score, best_faq = 0.0, None
    for faq in faqs:
        try:
            faq_vec = json.loads(faq.embedding)
            score = _cosine_similarity(q_vec, faq_vec)
            if score > best_score:
                best_score, best_faq = score, faq
        except Exception:
            continue

    if best_score >= FAQ_MIN_SIMILARITY:
        return best_faq, best_score
    return None, best_score


def extract_key_facts(text: str) -> list[str]:
    """DB回答から数値・日付・電話番号などキーファクトを抽出する"""
    patterns = [
        r'\d{4}年\d{1,2}月\d{1,2}日',   # 2018年7月12日
        r'\d{4}年',                        # 2018年
        r'[\d,]+億[\d,]*万?円?',           # 3億2,000万円
        r'[\d,]+万円',                     # 5,000万円
        r'週\d+日',                        # 週3日
        r'\d+,\d{3}円',                   # 30,000円
        r'¥[\d,]+',                       # ¥30,000
        r'\d+名',                          # 87名
        r'\d+日(?!間)',                    # 25日（日間は除外）
        r'\d+日間',                        # 14日間
        r'\d+時間',                        # 2時間
        r'\d+%',                           # 80%
        r'\d{2,3}-\d{4}-\d{4}',          # 03-1234-5678
        r'\d{10,11}',                     # 電話番号数字のみ
    ]
    facts = []
    for pattern in patterns:
        facts.extend(re.findall(pattern, text))
    return list(dict.fromkeys(facts))  # 重複除去・順序保持


def call_chat_api(question: str) -> tuple[str, float, str | None]:
    payload = {
        "question": question,
        "model": MODEL,
        "timeout": TIMEOUT,
        "mode": "通常",
        "history": [],
    }
    start = time.time()
    full_response = ""
    error_msg = None

    try:
        with requests.post(
            CHAT_ENDPOINT,
            json=payload,
            stream=True,
            timeout=TIMEOUT + 10,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if "token" in data:
                    full_response += data["token"]
                elif "error" in data:
                    error_msg = data["error"]
                    break
                elif data.get("done"):
                    break
    except requests.exceptions.ConnectionError:
        error_msg = f"接続エラー: {CHAT_ENDPOINT} に接続できません。Djangoサーバーが起動しているか確認してください。"
    except requests.exceptions.Timeout:
        error_msg = "リクエストタイムアウト"
    except Exception as e:
        error_msg = f"予期しないエラー: {e}"

    duration = time.time() - start
    return full_response.strip(), round(duration, 2), error_msg


def evaluate(tc: dict, response: str, error: str | None, db_faq: object | None) -> dict:
    issues = []
    passed = True

    if error:
        return {"passed": False, "issues": [f"APIエラー: {error}"]}

    if not response:
        return {"passed": False, "issues": ["空の回答"]}

    expect_unknown = tc.get("expect_unknown", False)

    if expect_unknown:
        has_unknown_signal = any(kw in response for kw in UNKNOWN_KEYWORDS)
        if not has_unknown_signal:
            passed = False
            issues.append("範囲外の質問なのに断り文句がない")
    else:
        # NGパターンチェック
        ng_patterns = tc.get("ng_patterns", []) + GLOBAL_NG_PATTERNS
        for ng in ng_patterns:
            if ng in response:
                passed = False
                issues.append(f"NGパターン検出: 「{ng}」")

        # 手動指定キーワードチェック
        for kw in tc.get("expected_keywords", []):
            if kw not in response:
                passed = False
                issues.append(f"期待キーワードなし: 「{kw}」")

        # DB自動キーファクトチェック（expected_keywords が空の場合）
        if not tc.get("expected_keywords") and db_faq is not None:
            key_facts = extract_key_facts(db_faq.answer)
            for fact in key_facts:
                if fact not in response:
                    passed = False
                    issues.append(f"DBキーファクト不一致: 「{fact}」（DB回答: {db_faq.answer[:60]}…）")

    return {"passed": passed, "issues": issues}


def run_tests() -> list[dict]:
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        test_cases = json.load(f)

    results = []
    total = len(test_cases)

    print(f"\n{'='*60}")
    print(f"  qwen2.5-techbridge 回答品質テスト  ({total}件)")
    print(f"  エンドポイント: {CHAT_ENDPOINT}")
    print(f"{'='*60}\n")

    for i, tc in enumerate(test_cases, 1):
        tc_id = tc.get("id", f"tc{i:03d}")
        question = tc["question"]
        note = tc.get("note", "")

        print(f"[{i}/{total}] {tc_id}: {question}")
        if note:
            print(f"       ※ {note}")

        # DB検索
        db_faq, db_score = get_best_faq(question)
        if db_faq:
            print(f"       DB: [{db_score:.2f}] Q: {db_faq.question}")
            print(f"           A: {db_faq.answer[:80]}{'…' if len(db_faq.answer) > 80 else ''}")

        response, duration, error = call_chat_api(question)

        eval_result = evaluate(tc, response, error, db_faq)
        status = "PASS" if eval_result["passed"] else "FAIL"

        print(f"       → {status}  ({duration}s)")
        if not eval_result["passed"]:
            for issue in eval_result["issues"]:
                print(f"          ✗ {issue}")
        if response and not error:
            preview = response[:80].replace("\n", " ")
            print(f"          AI回答: {preview}{'...' if len(response) > 80 else ''}")
        elif error:
            print(f"          エラー: {error}")
        print()

        results.append({
            "id": tc_id,
            "question": question,
            "note": note,
            "status": status,
            "passed": eval_result["passed"],
            "issues": eval_result["issues"],
            "response": response,
            "duration_sec": duration,
            "error": error,
            "db_faq_question": db_faq.question if db_faq else "",
            "db_faq_answer": db_faq.answer if db_faq else "",
            "db_score": round(db_score, 3),
        })

    return results


def print_summary(results: list[dict]):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    print(f"{'='*60}")
    print(f"  結果サマリー")
    print(f"{'='*60}")
    print(f"  合計: {total}件  |  PASS: {passed}件  |  FAIL: {failed}件")
    print(f"  合格率: {passed/total*100:.1f}%")

    if failed > 0:
        print(f"\n  --- FAILしたケース ---")
        for r in results:
            if not r["passed"]:
                print(f"  [{r['id']}] {r['question']}")
                for issue in r["issues"]:
                    print(f"    ✗ {issue}")
    print(f"{'='*60}\n")


def save_results(results: list[dict]):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(os.path.dirname(__file__), f"test_results_{ts}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "executed_at": ts,
                "model": MODEL,
                "endpoint": CHAT_ENDPOINT,
                "total": len(results),
                "passed": sum(1 for r in results if r["passed"]),
                "failed": sum(1 for r in results if not r["passed"]),
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"  結果を保存しました: {output_path}")


def write_to_spreadsheet(results: list[dict], executed_at: str):
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"  スプシ書き出しスキップ（認証ファイルなし: {CREDENTIALS_PATH}）")
        return

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)

        sheet_name = "テスト結果"
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=12)

        header = ["実行日時", "テストID", "質問", "判定", "所要時間(秒)", "問題点", "AI回答", "DBマッチQ", "DB期待回答", "DBスコア"]
        existing = ws.row_values(1)
        if existing != header:
            ws.insert_row(header, index=1)

        rows = []
        for r in results:
            rows.append([
                executed_at,
                r["id"],
                r["question"],
                r["status"],
                r["duration_sec"],
                " / ".join(r["issues"]) if r["issues"] else "",
                r["response"] or r.get("error", ""),
                r.get("db_faq_question", ""),
                r.get("db_faq_answer", ""),
                r.get("db_score", ""),
            ])
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        print(f"  スプシに書き出しました: {len(rows)}件")
        print(f"  https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
    except Exception as e:
        print(f"  スプシ書き出しエラー: {e}")


if __name__ == "__main__":
    if not os.path.exists(QUESTIONS_FILE):
        print(f"エラー: {QUESTIONS_FILE} が見つかりません")
        sys.exit(1)

    results = run_tests()
    print_summary(results)
    executed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_results(results)
    write_to_spreadsheet(results, executed_at)
