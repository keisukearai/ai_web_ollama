"""
MCPサーバーへの HTTP クライアント

MCPサーバーが --transport streamable-http で起動している前提。
環境変数 MCP_SERVER_URL でエンドポイントを切り替える（デフォルト: localhost:8100）。

使い方:
    from api.mcp_client import call_get_company

    result = call_get_company('COMP001')
    if result['found']:
        print(result['company_name'])
"""
import json
import os
import uuid

import requests

_MCP_SERVER_URL = os.environ.get('MCP_SERVER_URL', 'http://localhost:8100/mcp')
_TIMEOUT = 10


def _call_tool(tool_name: str, arguments: dict) -> dict:
    """
    MCP Streamable HTTP トランスポート経由でツールを呼び出す。
    tools/call リクエストを送り、結果の content[0].text を JSON パースして返す。
    """
    payload = {
        'jsonrpc': '2.0',
        'id': str(uuid.uuid4()),
        'method': 'tools/call',
        'params': {
            'name': tool_name,
            'arguments': arguments,
        },
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
    }
    resp = requests.post(_MCP_SERVER_URL, json=payload, headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()

    body = resp.json()
    # エラーレスポンス
    if 'error' in body:
        raise RuntimeError(f"MCPエラー: {body['error']}")

    # 結果テキストを取り出す
    content = body.get('result', {}).get('content', [])
    if not content:
        raise RuntimeError('MCP レスポンスに content がありません')

    text = content[0].get('text', '{}')
    return json.loads(text)


def call_get_company(company_code: str) -> dict:
    """
    get_company tool を呼び出して企業情報を返す。
    MCPサーバーが停止中でも例外を外に出さず、found=False の dict を返す。
    """
    try:
        return _call_tool('get_company', {'company_code': company_code})
    except Exception as e:
        return {
            'found': False,
            'message': f'MCPサーバー呼び出し失敗: {e}',
        }
