#!/bin/bash
# git pull後の更新デプロイスクリプト
set -e

APP_DIR="/home/admin/ai_web_ollama"

echo "=== git pull ==="
cd "$APP_DIR"
git pull origin main

echo "=== Django マイグレーション ==="
cd "$APP_DIR/backend"
source venv/bin/activate
pip install -q -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
deactivate

echo "=== Next.js ビルド ==="
cd "$APP_DIR/frontend"
npm ci --silent
npm run build

echo "=== サービス再起動 ==="
sudo systemctl restart ai-django ai-nextjs

echo "=== 完了 ==="
