"""
get_company tool

入力: company_code (str)
出力: found(bool) + 企業情報フィールド群
"""
from mcp_server.db import fetch_company


def get_company(company_code: str) -> dict:
    """
    企業コードで企業情報を検索して返す。

    Args:
        company_code: 検索する企業コード（例: "COMP001"）

    Returns:
        found=True のとき企業情報フィールドを含む dict。
        found=False のとき {found: false, message: ...} のみ。
    """
    if not company_code or not company_code.strip():
        return {'found': False, 'message': 'company_code が空です'}

    row = fetch_company(company_code.strip())
    if row is None:
        return {
            'found': False,
            'message': f'企業コード "{company_code}" は見つかりませんでした',
        }

    return {
        'found':          True,
        'company_code':   row['company_code'],
        'company_name':   row['company_name'],
        'kot_host':       row['kot_host'],
        'kot_start_date': row['kot_start_date'],
        'kot_end_date':   row['kot_end_date'],
        'status':         row['status'],
    }
