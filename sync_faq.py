"""
スプレッドシートのFAQデータをDBに取り込み、
nomic-embed-text でベクトル埋め込みを生成してDBに保存するスクリプト。

使い方:
  python sync_faq.py

スプシを更新したら都度実行してください。
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
    """DBのFAQテーブルを洗い替え"""
    FAQ.objects.all().delete()
    FAQ.objects.bulk_create([
        FAQ(
            category=d['category'],
            question=d['question'],
            answer=d['answer'],
            row_number=d['row_number'],
            search_keywords=d.get('search_keywords', ''),
        )
        for d in data
    ])
    print(f'DB更新完了: {len(data)}件')


def generate_embeddings():
    """全FAQのベクトル埋め込みを生成してDBに保存"""
    faqs = list(FAQ.objects.all())
    print(f'   {len(faqs)}件の埋め込みを生成中...')

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


def main():
    print('=== sync_faq.py 開始 ===')

    print('① スプレッドシートからデータ取得中...')
    data = fetch_from_sheet()
    print(f'   {len(data)}件取得')

    print('② DBに取り込み中...')
    sync_to_db(data)

    print('③ ベクトル埋め込み生成中...')
    generate_embeddings()

    print('=== 完了 ===')


if __name__ == '__main__':
    main()
