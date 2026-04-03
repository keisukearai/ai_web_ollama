# AI Web Ollama セットアップ手順

## 概要

Ollama で動くローカル LLM (Gemma 3 4B) をバックエンドにした Web チャットアプリ。

| コンポーネント | 技術 | ポート |
|---|---|---|
| フロントエンド | Next.js 14 (App Router) | 3000 |
| バックエンド | Django 4.2 + DRF | 8000 |
| データベース | PostgreSQL | 5432 |
| LLM | Ollama (gemma3:4b) | 11434 |
| リバースプロキシ | nginx | 80 |

**サーバー:** `<SERVER_IP>`  
**Git:** `git@github.com:<USERNAME>/<REPO>.git`

---

## ディレクトリ構成

```
ai_web_ollama/
├── backend/              # Django アプリ
│   ├── config/           # settings, urls, wsgi
│   ├── api/              # モデル・ビュー・シリアライザ
│   ├── manage.py
│   └── requirements.txt
├── frontend/             # Next.js アプリ
│   └── src/
│       ├── app/          # App Router (page.tsx, layout.tsx)
│       └── lib/api.ts    # API クライアント
├── nginx/
│   └── default.conf      # リバースプロキシ設定
├── deploy/
│   ├── django.service    # systemd サービス (Gunicorn)
│   ├── nextjs.service    # systemd サービス (Next.js)
│   └── update.sh         # git pull 後の更新スクリプト
├── setup-server.sh       # 初回セットアップスクリプト
└── docs/
    └── setup.md          # この手順書
```

---

## API エンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| POST | `/api/chat/` | 質問を送り AI 応答を取得・DB保存 |
| GET | `/api/history/` | 会話履歴一覧 (limit パラメータ対応) |
| GET | `/api/models/` | Ollama の利用可能モデル一覧 |

### POST /api/chat/ リクエスト例

```json
{
  "question": "Pythonで素数を判定する関数を書いて",
  "model": "gemma3:4b"
}
```

### レスポンス例

```json
{
  "id": 1,
  "question": "Pythonで素数を判定する関数を書いて",
  "response": "def is_prime(n):\n...",
  "model_name": "gemma3:4b",
  "duration_ms": 34521,
  "created_at": "2026-04-03T10:00:00+09:00"
}
```

---

## 初回デプロイ手順

### 1. ローカルで作業（開発マシン）

```bash
# リポジトリをクローン
git clone git@github.com:<USERNAME>/<REPO>.git
cd ai_web_ollama
```

### 2. サーバーにSSH接続

```bash
ssh <USER>@<SERVER_IP>
```

### 3. リポジトリをサーバーにクローン

```bash
cd ~
git clone git@github.com:<USERNAME>/<REPO>.git
cd ai_web_ollama
```

> GitHub への SSH 接続には、サーバーの `~/.ssh/id_ed25519.pub` を GitHub の Deploy Keys に登録する必要あり。  
> 鍵生成: `ssh-keygen -t ed25519 -C "server-deploy"`

### 4. .env ファイルを作成

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

編集内容（最低限）：

```env
DJANGO_SECRET_KEY=<ランダムな50文字以上の文字列>
DB_PASSWORD=<任意のパスワード>
ALLOWED_HOSTS=<SERVER_IP>,localhost
CORS_ALLOWED_ORIGINS=http://<SERVER_IP>
```

`DJANGO_SECRET_KEY` の生成方法：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 5. ファイアウォール設定（UFW）

サーバー内のUFWでHTTP/HTTPSポートを開放する。

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status
```

開放後に以下が表示されればOK：

```
80/tcp                     ALLOW       Anywhere
443/tcp                    ALLOW       Anywhere
```

> **ConoHa VPS を使用している場合:**  
> コントロールパネル → ネットワーク → セキュリティグループ で以下のインバウンドルールを追加する。  
> UFW とセキュリティグループの**両方**を開放しないと外部から繋がらない。
>
> | 通信方向 | プロトコル | ポート | IP/CIDR |
> |---|---|---|---|
> | In (IPv4) | TCP | 80 | 0.0.0.0/0 |
> | In (IPv6) | TCP | 80 | ::/0 |
> | In (IPv4) | TCP | 443 | 0.0.0.0/0 |
> | In (IPv6) | TCP | 443 | ::/0 |

### 6. セットアップスクリプトを実行

```bash
chmod +x setup-server.sh
./setup-server.sh
```

スクリプトが行うこと：
1. PostgreSQL / Node.js / nginx インストール
2. PostgreSQL にDB・ユーザー作成
3. Python 仮想環境作成・Django マイグレーション実行
4. Next.js ビルド
5. nginx 設定コピー・再起動
6. systemd サービス登録・起動

### 7. 動作確認

```bash
# サービス状態確認
sudo systemctl status ai-django ai-nextjs nginx

# ログ確認
sudo journalctl -u ai-django -f
sudo journalctl -u ai-nextjs -f

# API疎通確認
curl http://localhost:8000/api/models/

# ブラウザでアクセス
# http://<SERVER_IP>
```

---

## 更新デプロイ手順（2回目以降）

```bash
ssh <USER>@<SERVER_IP>
cd ~/ai_web_ollama
chmod +x deploy/update.sh
./deploy/update.sh
```

または手動で：

```bash
git pull origin main
# Django
cd backend && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
deactivate
# Next.js
cd ../frontend && npm ci && npm run build
# 再起動
sudo systemctl restart ai-django ai-nextjs
```

---

## ドメイン設定

DNS で `<YOUR_DOMAIN>` を `<SERVER_IP>` に向けた後、nginx の `server_name` を変更する。

```bash
# nginx/default.conf の server_name を変更
server_name <YOUR_DOMAIN>;

# サーバーに反映
sudo cp ~/ai_web_ollama/nginx/default.conf /etc/nginx/sites-available/ai_web_ollama
sudo nginx -t && sudo systemctl reload nginx
```

`.env` のドメインも更新する：

```env
ALLOWED_HOSTS=<YOUR_DOMAIN>,localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://<YOUR_DOMAIN>
```

反映：

```bash
sudo systemctl restart ai-django
```

---

## トラブルシューティング

### Django が起動しない

```bash
# ログ確認
sudo journalctl -u ai-django -n 50

# よくある原因
# - .env の DB_PASSWORD が間違っている
# - PostgreSQL が起動していない
sudo systemctl start postgresql
```

### AI応答が遅い / タイムアウト

- CPU 推論のため 1 応答あたり **30〜60 秒** かかるのは正常
- nginx のタイムアウトは `proxy_read_timeout 300s` に設定済み
- Django の gunicorn タイムアウトも `--timeout 300` に設定済み

### Next.js ビルドが失敗する

```bash
# Node.js バージョン確認 (18以上推奨)
node --version
# npm キャッシュクリア
cd frontend && rm -rf node_modules .next && npm ci && npm run build
```

### PostgreSQL 接続エラー

```bash
# DB確認
sudo -u postgres psql -c "\l"
sudo -u postgres psql -c "\du"

# 手動でDB作成
sudo -u postgres psql -c "CREATE USER aiuser WITH PASSWORD 'your-password';"
sudo -u postgres psql -c "CREATE DATABASE ai_web_ollama OWNER aiuser;"
```

### GitHub SSH鍵の登録

```bash
# サーバーで鍵生成
ssh-keygen -t ed25519 -C "ai-server-deploy" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
# → 出力された公開鍵を GitHub > リポジトリ > Settings > Deploy keys に追加

# 接続確認
ssh -T git@github.com
```

---

## Ollama 関連

Ollama は別途インストール済み（`llm-setup.md` 参照）。

```bash
# サービス状態
sudo systemctl status ollama

# モデル確認
ollama list

# モデルを追加する場合
ollama pull qwen2.5:7b
```

利用可能モデルはブラウザの UI 上部のドロップダウンから切り替え可能。
