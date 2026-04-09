"""
qwen2.5-techbridge の回答品質自動テスト

使い方:
  python test_faq_quality.py

前提:
  - Django サーバーが起動済み（http://localhost:8000）
  - test_faq_questions.json が同じディレクトリにある

結果は test_results_<timestamp>.json にも保存されます。
"""

import json
import time
import datetime
import requests
import sys
import os

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
CHAT_ENDPOINT = f"{BASE_URL}/api/chat/"
MODEL = "qwen2.5-techbridge"
TIMEOUT = 120

QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "test_faq_questions.json")

# 汎用NGパターン（すべてのテストケースに共通で適用）
GLOBAL_NG_PATTERNS = [
    "エラー",
    "Ollama接続エラー",
    "タイムアウト",
]

# 回答が「範囲外」を示すとみなすキーワード（expect_unknown=True のケースで使用）
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


def call_chat_api(question: str) -> tuple[str, float, str | None]:
    """SSEエンドポイントを叩いて全トークンを結合して返す。
    Returns: (full_response, duration_sec, error_message)
    """
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


def evaluate(tc: dict, response: str, error: str | None) -> dict:
    """テストケースと回答からパス/フェイル判定を返す。"""
    issues = []
    passed = True

    if error:
        return {"passed": False, "issues": [f"APIエラー: {error}"]}

    if not response:
        return {"passed": False, "issues": ["空の回答"]}

    expect_unknown = tc.get("expect_unknown", False)

    if expect_unknown:
        # FAQ範囲外の質問 → UNKNOWN_KEYWORDS のどれかが含まれていれば合格
        has_unknown_signal = any(kw in response for kw in UNKNOWN_KEYWORDS)
        if not has_unknown_signal:
            passed = False
            issues.append(
                f"範囲外の質問なのに断り文句がない（期待: {UNKNOWN_KEYWORDS} のいずれか）"
            )
    else:
        # 通常のFAQ質問 → NGパターンが含まれていたらフェイル
        ng_patterns = tc.get("ng_patterns", []) + GLOBAL_NG_PATTERNS
        for ng in ng_patterns:
            if ng in response:
                passed = False
                issues.append(f"NGパターン検出: 「{ng}」")

        # expected_keywords チェック
        for kw in tc.get("expected_keywords", []):
            if kw not in response:
                passed = False
                issues.append(f"期待キーワードなし: 「{kw}」")

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

        response, duration, error = call_chat_api(question)

        eval_result = evaluate(tc, response, error)
        status = "PASS" if eval_result["passed"] else "FAIL"

        print(f"       → {status}  ({duration}s)")
        if not eval_result["passed"]:
            for issue in eval_result["issues"]:
                print(f"          ✗ {issue}")
        if response and not error:
            preview = response[:80].replace("\n", " ")
            print(f"          回答: {preview}{'...' if len(response) > 80 else ''}")
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


if __name__ == "__main__":
    if not os.path.exists(QUESTIONS_FILE):
        print(f"エラー: {QUESTIONS_FILE} が見つかりません")
        sys.exit(1)

    results = run_tests()
    print_summary(results)
    save_results(results)
