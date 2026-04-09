"""
DBの search_keywords をスプレッドシートD列に書き戻すスクリプト。

Django admin で FAQ の search_keywords を直接編集した後に実行すると、
スプレッドシートを DB と同期した状態に保てます。

使い方:
  python export_keywords_to_sheet.py
"""

import os
import sys

import django
import gspread
from google.oauth2.service_account import Credentials

# Django セットアップ
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.models import FAQ, AppConfig  # noqa: E402

import re  # noqa: E402

CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), 'backend', 'credentials', 'google_sheets.json')


def get_sheet():
    url = AppConfig.objects.filter(key='faq_spreadsheet_url').values_list('value', flat=True).first()
    if not url:
        print('ERROR: AppConfig に faq_spreadsheet_url が設定されていません')
        sys.exit(1)
    m = re.search(r'/spreadsheets/d/([^/]+)', url)
    if not m:
        print('ERROR: URLからスプレッドシートIDを取得できません')
        sys.exit(1)
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(m.group(1)).sheet1


def main():
    print('=== export_keywords_to_sheet.py 開始 ===')

    print('① DBからキーワード情報を取得中...')
    # row_number → search_keywords のマップを作成
    faqs = FAQ.objects.all().values('row_number', 'search_keywords')
    kw_map = {f['row_number']: f['search_keywords'] for f in faqs}
    with_kw = {row: kw for row, kw in kw_map.items() if kw}
    print(f'   キーワード登録済み: {len(with_kw)}件 / 全{len(kw_map)}件')

    print('② スプレッドシートのD列を更新中...')
    ws = get_sheet()

    # D1 にヘッダーがなければ追加
    header = ws.cell(1, 4).value
    if header != 'search_keywords':
        ws.update_cell(1, 4, 'search_keywords')
        print('   D1ヘッダーを設定しました')

    # バッチ更新用データを組み立て（変更があるセルのみ）
    updates = []
    all_rows = ws.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):  # 2行目以降
        current_kw = row[3].strip() if len(row) >= 4 else ''
        db_kw = kw_map.get(i, '')
        if current_kw != db_kw:
            updates.append({'range': f'D{i}', 'values': [[db_kw]]})

    if updates:
        ws.batch_update(updates)
        print(f'   {len(updates)}件のセルを更新しました')
        for u in updates:
            row_num = int(u['range'][1:])
            kw_val = u['values'][0][0]
            action = '設定' if kw_val else 'クリア'
            print(f'   {action}: row {row_num} → {repr(kw_val)}')
    else:
        print('   変更なし（スプシはDBと同期済みです）')

    print('=== 完了 ===')


if __name__ == '__main__':
    main()
