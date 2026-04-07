# 変更履歴 2026-04-08

## 1. 生成停止ボタン追加

- 生成中に送信ボタンが赤い **停止ボタン**（AlertTriangle アイコン）に切り替わる
- クライアント側で fetch を abort → Django の `GeneratorExit` → `resp.close()` で Ollama のストリームを即時停止
- 停止後は部分回答を画面に残し、フッターに `経過時間 · モデル名 · 停止` を表示
- ボタン色: `#b91c1c`（濃い赤）

**変更ファイル:** `frontend/src/lib/api.ts`, `frontend/src/app/page.tsx`

---

## 2. 送信キーを Ctrl+Enter に変更

- 変更前: Enter で送信 / Shift+Enter で改行
- 変更後: **Ctrl+Enter で送信 / Enter で改行**
- プレースホルダー・案内テキストも更新

**変更ファイル:** `frontend/src/app/page.tsx`

---

## 3. AI 回答の行間・段落間隔を縮小

- `.md p`: `margin: 0; line-height: 1.2`
- `.bubble-ai`: `line-height: 1.3`、`white-space: pre-wrap` を削除（タグ間の改行が可視化される問題を解消）

**変更ファイル:** `frontend/src/app/globals.css`

---

## 4. 生成中のスクロール制御

- ユーザーが上にスクロールすると自動スクロールを停止（過去の回答を確認可能）
- 下端から 100px 以内に戻ると自動スクロール再開
- 新しいメッセージ送信時はスクロール位置をリセット

**変更ファイル:** `frontend/src/app/page.tsx`

---

## 5. タイムアウト選択機能

- ヘッダーにタイムアウト選択プルダウンを追加
- 選択肢: **15 / 30 / 60 / 120 / 180 / 240 / 300 秒**（デフォルト 120 秒）
- フロントエンド・バックエンド双方に反映
- バグ修正: `useCallback` の依存配列に `timeoutSec` が抜けており常に 120 秒になっていた問題を修正

**変更ファイル:** `frontend/src/app/page.tsx`, `frontend/src/lib/api.ts`, `backend/api/views.py`

---

## 6. タイムアウト時の表示・DB保存

- タイムアウト時に部分回答を画面に残す（以前はすべてクリアされていた）
- フッターに `経過時間 · モデル名 · タイムアウト` を表示
- `Conversation` モデルに `timed_out` フィールド追加（`BooleanField`, デフォルト `False`）
- サーバー側タイムアウト時に部分レスポンスと経過時間を DB 保存
- Django 管理画面の一覧・フィルターに `timed_out` 列を追加

**変更ファイル:** `backend/api/models.py`, `backend/api/views.py`, `backend/api/admin.py`, `frontend/src/app/page.tsx`, `frontend/src/lib/api.ts`
**マイグレーション:** `backend/api/migrations/0004_conversation_timed_out.py`

---

## 7. 回答モード選択（要約 / 通常 / 深く）

- 入力エリア上部にモード選択ボタングループを追加
- デフォルト: **通常**
- 各モードのシステムプロンプト:
  - **要約**: 「回答は簡潔にまとめ、100〜150文字程度で答えてください。」
  - **通常**: システムメッセージなし
  - **深く**: 「詳しく、多角的な視点から丁寧に説明してください。」

**変更ファイル:** `frontend/src/app/page.tsx`, `frontend/src/lib/api.ts`, `backend/api/views.py`

---

## 8. モバイル対応

- ヘッダー: モバイルでは **Ollama バッジ・CPU/MEM ステータス** を非表示（タイトル・モデル選択・タイムアウト選択・テーマ・メニューは表示）
- CPU/MEM: モバイルでは入力エリア上部（モードボタン右端）に表示
- バブル最大幅: モバイル `92%` / デスクトップ `78%`
- フォントサイズ: モバイルで `textarea` / `input` / `select` を `16px` に設定し、iOS/Android の自動ズームを防止

**変更ファイル:** `frontend/src/app/page.tsx`, `frontend/src/app/globals.css`
