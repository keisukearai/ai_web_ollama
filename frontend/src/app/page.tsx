'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { sendChat, fetchHistory, fetchModels, Conversation } from '@/lib/api';

type Message = {
  role: 'user' | 'ai';
  content: string;
  duration_ms?: number | null;
  created_at?: string;
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('ja-JP', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [model, setModel] = useState('gemma3:4b');
  const [models, setModels] = useState<string[]>(['gemma3:4b']);
  const [history, setHistory] = useState<Conversation[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetchModels().then(setModels).catch(() => {});
    fetchHistory().then(setHistory).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const adjustTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  const handleSubmit = useCallback(async () => {
    const q = input.trim();
    if (!q || loading) return;

    setInput('');
    setError('');
    setLoading(true);
    setMessages(prev => [...prev, { role: 'user', content: q }]);

    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    try {
      const conv = await sendChat(q, model);
      setMessages(prev => [...prev, {
        role: 'ai',
        content: conv.response,
        duration_ms: conv.duration_ms,
        created_at: conv.created_at,
      }]);
      setHistory(prev => [conv, ...prev]);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '不明なエラー';
      setError(msg);
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  }, [input, loading, model]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const loadConversation = (conv: Conversation) => {
    setMessages([
      { role: 'user', content: conv.question },
      { role: 'ai', content: conv.response, duration_ms: conv.duration_ms, created_at: conv.created_at },
    ]);
  };

  return (
    <>
      <header>
        <h1>AI Chat</h1>
        <select
          value={model}
          onChange={e => setModel(e.target.value)}
          style={{
            background: 'var(--surface2)', border: '1px solid var(--border)',
            color: 'var(--text)', borderRadius: '6px', padding: '4px 8px',
            fontSize: '0.8rem', cursor: 'pointer',
          }}
        >
          {models.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <span className="model-badge">Ollama</span>
      </header>

      <div className="main">
        <div className="chat-area">
          <div className="messages">
            {messages.length === 0 && (
              <div className="empty-state">
                <div className="icon">💬</div>
                <p>質問を入力して送信してください</p>
                <p style={{ fontSize: '0.8rem' }}>Shift+Enter で改行 / Enter で送信</p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`message ${msg.role}`}>
                <div className="bubble">{msg.content}</div>
                {msg.role === 'ai' && msg.duration_ms && (
                  <div className="meta">
                    {msg.created_at && formatDate(msg.created_at)} ・ {(msg.duration_ms / 1000).toFixed(1)}秒
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="message ai">
                <div className="bubble thinking">
                  <span /><span /><span />
                </div>
              </div>
            )}
            {error && <div className="error-msg">{error}</div>}
            <div ref={bottomRef} />
          </div>

          <div className="input-area">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => { setInput(e.target.value); adjustTextarea(); }}
              onKeyDown={handleKeyDown}
              placeholder="質問を入力... (Enter で送信)"
              disabled={loading}
              rows={1}
            />
            <button className="send" onClick={handleSubmit} disabled={loading || !input.trim()}>
              {loading ? '送信中' : '送信'}
            </button>
          </div>
        </div>

        <aside className="sidebar">
          <h2>履歴 ({history.length})</h2>
          <div className="history-list">
            {history.map(conv => (
              <div key={conv.id} className="history-item" onClick={() => loadConversation(conv)}>
                <div className="q">{conv.question}</div>
                <div className="date">{formatDate(conv.created_at)}</div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </>
  );
}
