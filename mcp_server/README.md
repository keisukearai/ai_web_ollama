# TechBridge MCP Server

社内AIチャットシステムのDB検索処理をMCPサーバーへ切り出したもの。  
独自Web画面以外のAIクライアント（Claude Desktop など）からも同じツールを使い回せる構成にする目的で導入。

---

## システム構成

```
独自Web画面
  ↓
Pythonプログラム（Django）
  ↓
MCPクライアント（api/mcp_client.py）
  ↓  HTTP（streamable-http）
自作MCPサーバー（mcp_server/server.py）
  ↓
DB検索（PostgreSQL / mcp_companies テーブル）
  ↓
MCPサーバーが結果を返す
  ↓
DjangoがOllama / Gemma 3へ渡して回答生成
```

---

## ディレクトリ構成

```
mcp_server/
├── server.py                    # MCPサーバー本体（FastMCP）
├── db.py                        # DB接続・固定SQLクエリ（SELECT専用）
├── tools/
│   ├── __init__.py
│   └── company.py               # get_company tool 実装
├── seed_data.py                 # テスト用ダミーデータ投入
├── create_companies_table.sql   # テーブル定義
├── requirements.txt
├── .env.example                 # 環境変数サンプル
└── README.md

backend/api/
├── mcp_client.py                # Django → MCPサーバー HTTP クライアント
├── views.py                     # CompanyView（/api/company/）追加済み
└── urls.py                      # /api/company/ エンドポイント追加済み
```

---

## セットアップ

### 1. ライブラリインストール

```bash
pip install fastmcp psycopg2-binary python-dotenv
```

### 2. 環境変数設定

```bash
cp mcp_server/.env.example mcp_server/.env
# .env を開いて DB_PASSWORD を実際の値に書き換える
```

`.env` の内容：

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ai_web_ollama
DB_USER=aiuser
DB_PASSWORD=実際のパスワード

MCP_HTTP_PORT=8100
```

### 3. テーブル作成

```bash
psql -U aiuser -d ai_web_ollama -f mcp_server/create_companies_table.sql
```

### 4. ダミーデータ投入（動作確認用）

```bash
python -m mcp_server.seed_data
```

投入されるデータ：

| company_code | company_name         | status     |
|--------------|----------------------|------------|
| COMP001      | 株式会社テックブリッジ | active     |
| COMP002      | 有限会社サンプル商事   | active     |
| COMP003      | 株式会社終了テスト     | terminated |
| COMP004      | 合同会社休止中         | suspended  |

---

## 起動方法

### stdio モード（MCP Inspector / Claude Desktop 向け）

```bash
python -m mcp_server.server
```

### HTTP モード（Django クライアント向け）

```bash
python -m mcp_server.server --transport streamable-http
# → http://localhost:8100/mcp でリッスン開始
```

---

## MCP Inspector での動作確認

Node.js が必要（`node -v` で確認）。

```bash
# 方法1: npx（推奨）
npx @modelcontextprotocol/inspector python -m mcp_server.server

# 方法2: fastmcp の dev コマンド
mcp dev mcp_server/server.py
```

起動後にブラウザで `http://localhost:5173` を開く。

1. 左メニュー **Tools** → `get_company` を選択
2. `company_code` に `COMP001` と入力して実行
3. 以下が返れば成功

```json
{
  "found": true,
  "company_code": "COMP001",
  "company_name": "株式会社テックブリッジ",
  "kot_host": "techbridge.kotaiwan.com",
  "kot_start_date": "2020-04-01",
  "kot_end_date": null,
  "status": "active"
}
```

存在しないコードを入力した場合：

```json
{
  "found": false,
  "message": "企業コード \"XXXXXX\" は見つかりませんでした"
}
```

---

## Django API での動作確認

MCPサーバーを HTTP モードで起動した状態で：

```bash
# 企業情報取得
curl "http://localhost:8000/api/company/?code=COMP001"

# 存在しないコード
curl "http://localhost:8000/api/company/?code=XXXXXX"

# code パラメータなし → 400
curl "http://localhost:8000/api/company/"
```

---

## tool 仕様

### `get_company`

企業コードでDBを検索し、企業情報を返す。

**入力**

| パラメータ    | 型     | 説明                    |
|--------------|--------|-------------------------|
| company_code | string | 検索する企業コード（必須）|

**出力（found=true）**

| フィールド      | 型           | 説明                                      |
|----------------|--------------|-------------------------------------------|
| found          | boolean      | `true`                                    |
| company_code   | string       | 企業コード                                |
| company_name   | string       | 企業名                                    |
| kot_host       | string\|null | KOT ホスト名                              |
| kot_start_date | string\|null | KOT 利用開始日（YYYY-MM-DD）              |
| kot_end_date   | string\|null | KOT 利用終了日（YYYY-MM-DD、継続中は null）|
| status         | string       | `active` / `suspended` / `terminated`    |

**出力（found=false）**

| フィールド | 型      | 説明                   |
|-----------|---------|------------------------|
| found     | boolean | `false`                |
| message   | string  | 見つからない理由のメッセージ |

---

## 制約事項

- **読み取り専用**：SELECT のみ。UPDATE / DELETE / INSERT は禁止
- **固定SQL**：任意SQLの実行は不可（`db.py` に記述された固定クエリのみ）
- DBユーザーは参照専用権限を想定

---

## 将来の tool 追加方法

### 例: `get_invoice` を追加する場合

**1. SQL を `db.py` に追加**

```python
_SQL_GET_INVOICE = """
SELECT invoice_id, company_code, amount, issued_date, status
FROM mcp_invoices
WHERE invoice_id = %s
LIMIT 1
"""

def fetch_invoice(invoice_id: str) -> dict | None:
    with _get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_SQL_GET_INVOICE, (invoice_id,))
            row = cur.fetchone()
    return dict(row) if row else None
```

**2. tool ファイルを作成**

```bash
# mcp_server/tools/invoice.py を作成
```

**3. `server.py` に登録**

```python
@mcp.tool()
def get_invoice(invoice_id: str) -> dict:
    """請求書IDで請求情報を取得する。"""
    from mcp_server.tools.invoice import get_invoice as _get_invoice
    return _get_invoice(invoice_id)
```

**4. Django クライアントに追加**

```python
# api/mcp_client.py に追加
def call_get_invoice(invoice_id: str) -> dict:
    try:
        return _call_tool('get_invoice', {'invoice_id': invoice_id})
    except Exception as e:
        return {'found': False, 'message': f'MCPサーバー呼び出し失敗: {e}'}
```

既存コードへの影響はゼロ。
