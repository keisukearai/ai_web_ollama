# LLMサーバーセットアップ手順

## 環境

| 項目 | 内容 |
|------|------|
| サーバー | <SERVER_IP> |
| OS | Ubuntu 24.04.4 LTS |
| CPU | Intel Xeon (Icelake) 6コア |
| RAM | 12GB |
| GPU | なし（CPU推論） |
| Disk | 99GB（空き89GB） |

---

## 選定モデル：Gemma 3 4B

Google が 2025年3月に公開した最新モデル。CPU 専用環境でも動作する量子化版（3.3GB）。

- 多言語対応（日本語 OK）
- CPU 推論でも実用的なクオリティ
- 12GB RAM に余裕で収まるサイズ

---

## 手順

### 1. SSH接続

```bash
ssh <USER>@<SERVER_IP>
```

### 2. sudo のパスワードなし設定（インストール用に一時設定）

インストールスクリプト内部で sudo が呼ばれるため、事前に NOPASSWD 設定を追加する。

```bash
echo "admin ALL=(ALL) NOPASSWD:ALL" | sudo -S tee /etc/sudoers.d/admin-tmp
```

### 3. Ollama のインストール

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

インストール確認：

```bash
ollama --version
# => Warning: client version is 0.20.0
```

### 4. systemd サービスの作成・起動

インストールスクリプトがサービスファイルを自動生成しない場合、手動で作成する。

```bash
sudo tee /etc/systemd/system/ollama.service > /dev/null << 'EOF'
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

[Install]
WantedBy=default.target
EOF
```

ollama ユーザー作成（存在しない場合）：

```bash
sudo useradd -r -s /bin/false -m -d /usr/share/ollama ollama
```

サービス有効化・起動：

```bash
sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl start ollama
sudo systemctl status ollama
```

### 5. Gemma 3 4B モデルのダウンロード

3.3GB のダウンロードが発生するため、nohup でバックグラウンド実行する。

```bash
nohup ollama pull gemma3:4b > /tmp/ollama_pull.log 2>&1 &
```

進捗確認：

```bash
# プロセスが残っている間はダウンロード中
ps aux | grep "ollama pull" | grep -v grep

# ログ確認
cat /tmp/ollama_pull.log | strings | grep -E '[0-9]+%|success|error' | tail -5
```

完了確認：

```bash
ollama list
# => gemma3:4b    a2af6cc3eb7f    3.3 GB    ...
```

### 6. 動作確認

#### CLI から実行

```bash
ollama run gemma3:4b "日本語で自己紹介してください。3文以内で。"
```

#### REST API から実行

```bash
curl http://localhost:11434/api/generate \
  -d '{"model":"gemma3:4b","prompt":"日本語で自己紹介してください。3文以内で。","stream":false}'
```

レスポンス例（実際の動作結果）：

```
私はGoogleによってトレーニングされた、大規模言語モデルです。
様々な質問に答えたり、テキストを作成したりすることができます。
あなたとお話しできて嬉しいです！
```

CPU推論での処理時間：約35秒

---

## API エンドポイント一覧

| エンドポイント | 説明 |
|---------------|------|
| `POST /api/generate` | テキスト生成（非チャット） |
| `POST /api/chat` | チャット形式 |
| `GET /api/tags` | インストール済みモデル一覧 |
| `POST /api/pull` | モデルダウンロード |

Ollama はデフォルトで `http://127.0.0.1:11434` でリッスン。

---

## 外部からアクセスしたい場合

`/etc/systemd/system/ollama.service` の `[Service]` セクションに追記：

```ini
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

反映：

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

> 注意：セキュリティグループ・ファイアウォールで 11434 ポートを開放すること。

---

## モデルの追加候補（CPU 12GB 向け）

| モデル | サイズ | 特徴 |
|--------|--------|------|
| `gemma3:4b` | 3.3GB | 現在インストール済み。多言語・高品質 |
| `qwen2.5:7b` | 4.7GB | Alibaba製、コーディング・推論が得意 |
| `llama3.2:3b` | 2.0GB | Meta製、軽量・高速 |
| `phi4:14b` | 9.1GB | Microsoft製、高推論能力（RAM ギリギリ） |
