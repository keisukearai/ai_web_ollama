"""
スプレッドシートのFAQデータをDBに取り込み、
nomic-embed-text でベクトル埋め込みを生成してDBに保存するスクリプト。

使い方:
  python sync_faq.py

スプシを更新したら都度実行してください。

search_keywords の自動生成:
  スプシD列が空のFAQに対して LLM がキーワードを自動生成します。
  DBにすでにキーワードが入っているFAQはスキップ（再生成しない）。
  スプシD列に手動設定した値は常に優先されます。
"""
import json
import os
import sys

import django
import gspread
import requests
from google.oauth2.service_account import Credentials

# Django セットアップ
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings  # noqa: E402
from api.models import FAQ, AppConfig  # noqa: E402

CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), 'backend', 'credentials', 'google_sheets.json')
EMBED_MODEL = 'nomic-embed-text'
KEYWORD_MODEL = 'qwen2.5:1.5b'
OLLAMA_URL = getattr(settings, 'OLLAMA_URL', 'http://localhost:11434')


def fetch_from_sheet():
    """スプレッドシートからFAQデータを取得する"""
    url = AppConfig.objects.filter(key='faq_spreadsheet_url').values_list('value', flat=True).first()
    if not url:
        print('ERROR: AppConfig に faq_spreadsheet_url が設定されていません')
        sys.exit(1)

    import re
    m = re.search(r'/spreadsheets/d/([^/]+)', url)
    if not m:
        print('ERROR: faq_spreadsheet_url からIDを抽出できませんでした')
        sys.exit(1)

    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(m.group(1))
    rows = sh.sheet1.get_all_values()

    data = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) >= 3 and row[0].strip() and row[1].strip() and row[2].strip():
            data.append({
                'row_number': i,
                'category': row[0].strip(),
                'question': row[1].strip(),
                'answer': row[2].strip(),
                'search_keywords': row[3].strip() if len(row) >= 4 else '',
            })
    return data


def sync_to_db(data):
    """スプシとDBを差分比較して追加・更新・削除する。戻り値: 変更があったFAQのIDセット"""
    sheet_by_row = {d['row_number']: d for d in data}
    db_by_row = {faq.row_number: faq for faq in FAQ.objects.all()}

    sheet_rows = set(sheet_by_row)
    db_rows = set(db_by_row)

    to_delete = db_rows - sheet_rows
    to_add = sheet_rows - db_rows
    to_check = sheet_rows & db_rows

    changed_ids = set()

    # 削除
    if to_delete:
        FAQ.objects.filter(row_number__in=to_delete).delete()
        print(f'   削除: {len(to_delete)}件')

    # 新規追加
    new_faqs = []
    for row_num in to_add:
        d = sheet_by_row[row_num]
        new_faqs.append(FAQ(
            category=d['category'],
            question=d['question'],
            answer=d['answer'],
            row_number=d['row_number'],
            search_keywords=d.get('search_keywords', ''),
        ))
    if new_faqs:
        created = FAQ.objects.bulk_create(new_faqs)
        changed_ids.update(f.id for f in created)
        print(f'   追加: {len(new_faqs)}件')

    # 更新（内容が変わったもの）
    updated = 0
    for row_num in to_check:
        d = sheet_by_row[row_num]
        faq = db_by_row[row_num]
        fields = []
        if faq.category != d['category']:
            faq.category = d['category']
            fields.append('category')
        if faq.question != d['question']:
            faq.question = d['question']
            fields.append('question')
        if faq.answer != d['answer']:
            faq.answer = d['answer']
            fields.append('answer')
        # スプシD列が空でない場合は上書き
        sheet_kw = d.get('search_keywords', '')
        if sheet_kw and faq.search_keywords != sheet_kw:
            faq.search_keywords = sheet_kw
            fields.append('search_keywords')
        if fields:
            faq.save(update_fields=fields)
            changed_ids.add(faq.id)
            updated += 1

    if updated:
        print(f'   更新: {updated}件')

    no_change = len(to_check) - updated
    print(f'   変更なし: {no_change}件（スキップ）')
    print(f'DB差分更新完了: 合計{len(data)}件')
    return changed_ids


def generate_embeddings(changed_ids=None):
    """FAQのベクトル埋め込みを生成してDBに保存。changed_ids指定時は対象を絞る"""
    if changed_ids is not None:
        faqs = list(FAQ.objects.filter(id__in=changed_ids))
        print(f'   {len(faqs)}件の埋め込みを生成中（差分）...')
    else:
        faqs = list(FAQ.objects.all())
        print(f'   {len(faqs)}件の埋め込みを生成中...')

    if not faqs:
        print('   埋め込み生成対象なし')
        return

    for i, faq in enumerate(faqs, 1):
        text = f"{faq.category} {faq.question} {faq.answer}"
        resp = requests.post(
            f'{OLLAMA_URL}/api/embed',
            json={'model': EMBED_MODEL, 'input': text},
            timeout=30,
        )
        resp.raise_for_status()
        embedding = resp.json()['embeddings'][0]
        faq.embedding = json.dumps(embedding)
        faq.save(update_fields=['embedding'])
        if i % 20 == 0 or i == len(faqs):
            print(f'   {i}/{len(faqs)}件完了')

    print(f'埋め込み生成完了: {len(faqs)}件')


# キーワードとして使わない汎用語
_GENERIC_WORDS = {'会社', 'テックブリッジ', 'TechBridge', 'する', 'ある', 'ない', 'もの', 'こと', 'ため', 'お願い'}


def generate_keywords_with_llm(question: str, answer: str) -> str:
    """LLMを使ってFAQの検索キーワードを自動生成する"""
    prompt = (
        f"以下のFAQについて、ユーザーが検索で使いそうな日本語キーワードを3個だけカンマ区切りで出力してください。\n"
        f"キーワードのみ出力し、説明・番号・記号は不要です。\n\n"
        f"Q: {question}\n"
        f"A: {answer}\n\n"
        f"キーワード（3個）:"
    )
    try:
        resp = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={'model': KEYWORD_MODEL, 'prompt': prompt, 'stream': False},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json().get('response', '').strip()
        # 最初の行だけ使い、カンマで分割して3個に制限
        first_line = raw.split('\n')[0].strip()
        parts = [kw.strip() for kw in first_line.split(',')]
        # 汎用語・長すぎるもの・空文字を除去
        parts = [kw for kw in parts if kw and kw not in _GENERIC_WORDS and len(kw) <= 10]
        # 最大3個
        parts = parts[:3]
        return ','.join(parts)
    except Exception as e:
        print(f'   警告: キーワード生成失敗 ({e})')
        return ''


def generate_auto_keywords(changed_ids=None):
    """search_keywords が空のFAQにLLMでキーワードを自動生成する。changed_ids指定時は対象を絞る"""
    if changed_ids is not None:
        targets = list(FAQ.objects.filter(id__in=changed_ids, search_keywords=''))
    else:
        targets = list(FAQ.objects.filter(search_keywords=''))

    if not targets:
        print('   自動生成対象なし（全件にキーワードあり）')
        return

    print(f'   {len(targets)}件のキーワードを自動生成中...')
    generated = 0
    for i, faq in enumerate(targets, 1):
        keywords = generate_keywords_with_llm(faq.question, faq.answer)
        if keywords:
            faq.search_keywords = keywords
            faq.save(update_fields=['search_keywords'])
            generated += 1
        if i % 20 == 0 or i == len(targets):
            print(f'   {i}/{len(targets)}件処理済み')

    print(f'   キーワード自動生成完了: {generated}件')


def main():
    print('=== sync_faq.py 開始 ===')

    print('① スプレッドシートからデータ取得中...')
    data = fetch_from_sheet()
    print(f'   {len(data)}件取得')

    print('② DBに差分取り込み中...')
    changed_ids = sync_to_db(data)

    if not changed_ids:
        print('変更なし。処理を終了します。')
        print('=== 完了 ===')
        return

    print(f'③ ベクトル埋め込み生成中（変更{len(changed_ids)}件のみ）...')
    generate_embeddings(changed_ids)

    print('④ search_keywords 自動生成中（変更分でスプシD列が空のFAQのみ）...')
    generate_auto_keywords(changed_ids)

    print('=== 完了 ===')


if __name__ == '__main__':
    main()
