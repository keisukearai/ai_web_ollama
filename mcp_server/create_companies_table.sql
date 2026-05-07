-- MCP用 企業情報テーブル
-- 実行: psql -U aiuser -d ai_web_ollama -f create_companies_table.sql

CREATE TABLE IF NOT EXISTS mcp_companies (
    id          SERIAL PRIMARY KEY,
    company_code VARCHAR(50) UNIQUE NOT NULL,
    company_name VARCHAR(200) NOT NULL,
    kot_host     VARCHAR(200),
    kot_start_date DATE,
    kot_end_date   DATE,
    status       VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  mcp_companies IS 'MCP get_company tool 用の企業マスタ';
COMMENT ON COLUMN mcp_companies.company_code  IS '企業コード（一意）';
COMMENT ON COLUMN mcp_companies.company_name  IS '企業名';
COMMENT ON COLUMN mcp_companies.kot_host      IS 'KOT ホスト名';
COMMENT ON COLUMN mcp_companies.kot_start_date IS 'KOT 利用開始日';
COMMENT ON COLUMN mcp_companies.kot_end_date   IS 'KOT 利用終了日（NULL=継続中）';
COMMENT ON COLUMN mcp_companies.status        IS '利用状態: active / suspended / terminated';
