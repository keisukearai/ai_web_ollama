"""
TechBridge MCPサーバー

起動方法:
  # stdio（MCP Inspector / Claude Desktop 向け）
  python -m mcp_server.server

  # HTTP（Django クライアント向け、ポートは .env の MCP_HTTP_PORT）
  python -m mcp_server.server --transport streamable-http

  # MCP Inspector で直接確認
  mcp dev mcp_server/server.py
  または
  npx @modelcontextprotocol/inspector python -m mcp_server.server
"""
import os
import sys
from fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

mcp = FastMCP(
    name='TechBridge MCP Server',
    instructions='企業情報・バッチ状態などを照会する社内ツール群を提供します。',
)


# ─── tools ───────────────────────────────────────────────────────────────────

@mcp.tool()
def get_company(company_code: str) -> dict:
    """
    企業コードで企業情報を取得する。

    Args:
        company_code: 検索する企業コード（例: "COMP001"）

    Returns:
        found=True のとき company_name / kot_host / kot_start_date /
        kot_end_date / status を含む dict。
        found=False のとき message フィールドのみ。
    """
    from mcp_server.tools.company import get_company as _get_company
    return _get_company(company_code)


# ─── エントリーポイント ───────────────────────────────────────────────────────

if __name__ == '__main__':
    transport = 'stdio'
    port = int(os.environ.get('MCP_HTTP_PORT', 8100))

    if '--transport' in sys.argv:
        idx = sys.argv.index('--transport')
        transport = sys.argv[idx + 1]

    if transport == 'streamable-http':
        mcp.run(transport='streamable-http', port=port)
    else:
        mcp.run(transport='stdio')
