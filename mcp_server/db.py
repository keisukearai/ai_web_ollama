"""
DB接続・固定SQLクエリ（SELECT専用）
psycopg2 直接接続。Django ORM には依存しない。
"""
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

_SQL_GET_COMPANY = """
SELECT
    company_code,
    company_name,
    kot_host,
    kot_start_date,
    kot_end_date,
    status
FROM mcp_companies
WHERE company_code = %s
LIMIT 1
"""


def _get_connection():
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', 5432)),
        dbname=os.environ.get('DB_NAME', 'ai_web_ollama'),
        user=os.environ.get('DB_USER', 'aiuser'),
        password=os.environ.get('DB_PASSWORD', ''),
    )


def fetch_company(company_code: str) -> dict | None:
    """企業コードで1件検索。見つからなければ None を返す。"""
    with _get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_SQL_GET_COMPANY, (company_code,))
            row = cur.fetchone()
    if row is None:
        return None
    return {
        'company_code':   row['company_code'],
        'company_name':   row['company_name'],
        'kot_host':       row['kot_host'],
        'kot_start_date': str(row['kot_start_date']) if row['kot_start_date'] else None,
        'kot_end_date':   str(row['kot_end_date'])   if row['kot_end_date']   else None,
        'status':         row['status'],
    }
