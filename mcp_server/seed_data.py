"""
テスト用ダミーデータを mcp_companies に投入するスクリプト

実行: python -m mcp_server.seed_data
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

DUMMY_COMPANIES = [
    ('COMP001', '株式会社テックブリッジ',    'techbridge.kotaiwan.com', '2020-04-01', None,         'active'),
    ('COMP002', '有限会社サンプル商事',       'sample.kotaiwan.com',     '2021-06-01', None,         'active'),
    ('COMP003', '株式会社終了テスト',         'ended.kotaiwan.com',      '2019-01-01', '2023-12-31', 'terminated'),
    ('COMP004', '合同会社休止中',             None,                      '2022-03-01', None,         'suspended'),
]

SQL_UPSERT = """
INSERT INTO mcp_companies
    (company_code, company_name, kot_host, kot_start_date, kot_end_date, status)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (company_code) DO UPDATE SET
    company_name   = EXCLUDED.company_name,
    kot_host       = EXCLUDED.kot_host,
    kot_start_date = EXCLUDED.kot_start_date,
    kot_end_date   = EXCLUDED.kot_end_date,
    status         = EXCLUDED.status
"""

if __name__ == '__main__':
    conn = psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', 5432)),
        dbname=os.environ.get('DB_NAME', 'ai_web_ollama'),
        user=os.environ.get('DB_USER', 'aiuser'),
        password=os.environ.get('DB_PASSWORD', ''),
    )
    with conn:
        with conn.cursor() as cur:
            cur.executemany(SQL_UPSERT, DUMMY_COMPANIES)
    conn.close()
    print(f'{len(DUMMY_COMPANIES)} 件を投入しました')
    for row in DUMMY_COMPANIES:
        print(f'  {row[0]}: {row[1]} ({row[5]})')
