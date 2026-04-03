'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { sendChatStream, fetchHistory, fetchModels, Conversation } from '@/lib/api';

type Message = {
  role: 'user' | 'ai';
  content: string;
  duration_ms?: number | null;
  ip_address?: string | null;
  created_at?: string;
  streaming?: boolean;
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('ja-JP', {
    year: 'numeric', month: '2-digit', day: '2-digit',
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
  const [isDark, setIsDark] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const saved = localStorage.getItem('theme');
    const dark = saved ? saved === 'dark' : true;
    setIsDark(dark);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  }, []);

  const toggleTheme = () => {
    const next = !isDark;
    setIsDark(next);
    const theme = next ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  };

  useEffect(() => {
    fetchModels().then(setModels).catch(() => {});
    fetchHistory().then(setHistory).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    // ユーザーメッセージ + 空のAIメッセージを追加
    setMessages(prev => [
      ...prev,
      { role: 'user', content: q },
      { role: 'ai', content: '', streaming: true },
    ]);

    let accumulated = '';

    await sendChatStream(
      q,
      model,
      (token) => {
        accumulated += token;
        setMessages(prev => {
          const msgs = [...prev];
          const last = msgs[msgs.length - 1];
          if (last?.role === 'ai') {
            msgs[msgs.length - 1] = { ...last, content: accumulated };
          }
          return msgs;
        });
      },
      (data) => {
        setMessages(prev => {
          const msgs = [...prev];
          const last = msgs[msgs.length - 1];
          if (last?.role === 'ai') {
            msgs[msgs.length - 1] = {
              ...last,
              streaming: false,
              duration_ms: data.duration_ms,
              ip_address: data.ip_address,
              created_at: data.created_at,
            };
          }
          return msgs;
        });
        setHistory(prev => [{
          id: data.id,
          question: q,
          response: accumulated,
          model_name: model,
          duration_ms: data.duration_ms,
          ip_address: data.ip_address,
          created_at: data.created_at,
        }, ...prev]);
        setLoading(false);
      },
      (msg) => {
        setError(msg);
        setMessages(prev => prev.slice(0, -2));
        setLoading(false);
      },
    );
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
        <button className="theme-toggle" onClick={toggleTheme} title="テーマ切り替え">
          {isDark ? '☀️' : '🌙'}
        </button>
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
                {msg.streaming && msg.content === '' ? (
                  <div className="bubble thinking">
                    <span /><span /><span />
                  </div>
                ) : (
                  <div className="bubble">{msg.content}</div>
                )}
                {msg.role === 'ai' && !msg.streaming && msg.duration_ms && (
                  <div className="meta">
                    {msg.created_at && formatDate(msg.created_at)} ・ {(msg.duration_ms / 1000).toFixed(1)}sec
                  </div>
                )}
              </div>
            ))}
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
              {loading ? '生成中' : '送信'}
            </button>
          </div>
        </div>

        <aside className="sidebar">
          <h2>履歴 ({history.length})</h2>
          <div className="history-list">
            {history.map(conv => (
              <div key={conv.id} className="history-item" onClick={() => loadConversation(conv)}>
                <div className="q">{conv.question}</div>
                <div className="date">
                  {formatDate(conv.created_at)}
                  {conv.ip_address && <> ・ {conv.ip_address}</>}
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </>
  );
}
