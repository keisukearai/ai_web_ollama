"""
スプレッドシートのFAQデータをDBに取り込み、Modelfileを生成して
gemma3-techbridge カスタムモデルを作成するスクリプト。

使い方:
  python sync_faq.py

スプシを更新したら都度実行してください。
"""
import os
import sys
import subprocess
from collections import defaultdict

import django
import gspread
from google.oauth2.service_account import Credentials

# Django セットアップ
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.models import FAQ, AppConfig  # noqa: E402

CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), 'backend', 'credentials', 'google_sheets.json')
MODELFILE_PATH = os.path.join(os.path.dirname(__file__), 'Modelfile')
CUSTOM_MODEL_NAME = 'qwen2.5-techbridge'
BASE_MODEL = 'qwen2.5:1.5b'

MAX_FAQ_ITEMS = 50       # Modelfileに注入する最大件数
MAX_PER_CATEGORY = 6    # カテゴリごとの最大件数

SYSTEM_PROMPT_HEADER = """あなたは株式会社テックブリッジ（TechBridge Inc.）の社内アシスタントAIです。
以下のFAQデータに基づいて正確に回答してください。
FAQに記載のない質問には「その情報は持ち合わせていません」と答えてください。

--- FAQ データ ---
"""

SYSTEM_PROMPT_FOOTER = """--- FAQ データ終了 ---

回答は簡潔かつ丁寧にしてください。"""


def fetch_from_sheet():
    """スプレッドシートからFAQデータを取得する"""
    url = AppConfig.objects.filter(key='faq_spreadsheet_url').values_list('value', flat=True).first()
    if not url:
        print('ERROR: AppConfig に faq_spreadsheet_url が設定されていません')
        sys.exit(1)

    import re
    m = re.search(r'/spreadsheets/d/([^/]+)', url)
    if not m:
        print('ERROR: spreadsheet_url からIDを抽出できませんでした')
        sys.exit(1)
    spreadsheet_id = m.group(1)

    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    rows = sh.sheet1.get_all_values()

    # 1行目はヘッダー（カテゴリ/質問/回答）をスキップ
    data = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) >= 3 and row[0].strip() and row[1].strip() and row[2].strip():
            data.append({
                'row_number': i,
                'category': row[0].strip(),
                'question': row[1].strip(),
                'answer': row[2].strip(),
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
        )
        for d in data
    ])
    print(f'DB更新完了: {len(data)}件')


def select_representative_faqs():
    """カテゴリごとに最大 MAX_PER_CATEGORY 件、合計 MAX_FAQ_ITEMS 件に絞る"""
    category_map = defaultdict(list)
    for faq in FAQ.objects.all():
        category_map[faq.category].append(faq)

    selected = []
    for items in category_map.values():
        selected.extend(items[:MAX_PER_CATEGORY])
        if len(selected) >= MAX_FAQ_ITEMS:
            break

    return selected[:MAX_FAQ_ITEMS]


def generate_modelfile():
    """代表FAQからModelfileを生成"""
    faqs = select_representative_faqs()

    faq_text = ''
    current_category = None
    for faq in faqs:
        if faq.category != current_category:
            faq_text += f'\n【{faq.category}】\n'
            current_category = faq.category
        faq_text += f'Q: {faq.question}\nA: {faq.answer}\n'

    system_prompt = SYSTEM_PROMPT_HEADER + faq_text + SYSTEM_PROMPT_FOOTER
    modelfile_content = f'FROM {BASE_MODEL}\nPARAMETER num_ctx 4096\nSYSTEM """{system_prompt}"""\n'

    with open(MODELFILE_PATH, 'w', encoding='utf-8') as f:
        f.write(modelfile_content)
    print(f'Modelfile生成完了: {MODELFILE_PATH}（{len(faqs)}件使用 / 全{FAQ.objects.count()}件中）')


def create_ollama_model():
    """ollama create でカスタムモデルを作成"""
    print(f'ollama create {CUSTOM_MODEL_NAME} を実行中...')
    result = subprocess.run(
        ['ollama', 'create', CUSTOM_MODEL_NAME, '-f', MODELFILE_PATH],
        capture_output=False,
    )
    if result.returncode == 0:
        print(f'モデル作成完了: {CUSTOM_MODEL_NAME}')
    else:
        print(f'ERROR: ollama create に失敗しました (code={result.returncode})')
        sys.exit(1)


def main():
    print('=== sync_faq.py 開始 ===')

    print('① スプレッドシートからデータ取得中...')
    data = fetch_from_sheet()
    print(f'   {len(data)}件取得')

    print('② DBに取り込み中...')
    sync_to_db(data)

    print('③ Modelfile生成中...')
    generate_modelfile()

    print('④ ollama create 実行中...')
    create_ollama_model()

    print('=== 完了 ===')


if __name__ == '__main__':
    main()
