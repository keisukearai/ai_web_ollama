#!/bin/bash
set -e

APP_DIR="/home/admin/ai_web_ollama"
echo "=== [1/7] パッケージインストール ==="
sudo apt-get update -q
sudo apt-get install -y -q postgresql python3-pip python3-venv nodejs npm nginx

echo "=== [2/7] PostgreSQL セットアップ ==="
sudo systemctl enable postgresql
sudo systemctl start postgresql

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='aiuser'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER aiuser WITH PASSWORD '$(grep DB_PASSWORD $APP_DIR/backend/.env | cut -d= -f2)';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='ai_web_ollama'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE ai_web_ollama OWNER aiuser;"

echo "=== [3/7] Python 仮想環境 & Django セットアップ ==="
cd "$APP_DIR/backend"
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
deactivate

echo "=== [4/7] Node.js / Next.js ビルド ==="
cd "$APP_DIR/frontend"
npm ci --silent
npm run build

echo "=== [5/7] nginx 設定 ==="
sudo cp "$APP_DIR/nginx/default.conf" /etc/nginx/sites-available/ai_web_ollama
sudo ln -sf /etc/nginx/sites-available/ai_web_ollama /etc/nginx/sites-enabled/ai_web_ollama
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

echo "=== [6/7] systemd サービス登録 ==="
sudo cp "$APP_DIR/deploy/django.service" /etc/systemd/system/ai-django.service
sudo cp "$APP_DIR/deploy/nextjs.service" /etc/systemd/system/ai-nextjs.service
sudo systemctl daemon-reload
sudo systemctl enable ai-django ai-nextjs
sudo systemctl restart ai-django ai-nextjs

echo "=== [7/7] 完了 ==="
echo "アクセス: http://133.88.121.182"
