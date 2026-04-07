'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Sun, Moon, Menu, X, Send, AlertTriangle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { sendChatStream, fetchModels, fetchStats, Conversation, ServerStats } from '@/lib/api';

type Message = {
  role: 'user' | 'ai';
  content: string;
  duration_ms?: number | null;
  ip_address?: string | null;
  cpu_percent?: number | null;
  memory_percent?: number | null;
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
  const [stats, setStats] = useState<ServerStats | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const userScrolledRef = useRef(false);

  useEffect(() => {
    const saved = localStorage.getItem('theme');
    const dark = saved ? saved === 'dark' : true;
    setIsDark(dark);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  }, []);

  useEffect(() => {
    fetchModels().then(setModels).catch(() => {});
  }, []);

  useEffect(() => {
    fetchStats().then(setStats);
    const id = setInterval(() => fetchStats().then(setStats), 3000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!userScrolledRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const handleScroll = () => {
    const el = scrollContainerRef.current;
    if (!el) return;
    userScrolledRef.current = el.scrollHeight - el.scrollTop - el.clientHeight > 100;
  };

  const toggleTheme = () => {
    const next = !isDark;
    setIsDark(next);
    const theme = next ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  };

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
    setSidebarOpen(false);
    userScrolledRef.current = false;
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    setMessages(prev => [
      ...prev,
      { role: 'user', content: q },
      { role: 'ai', content: '', streaming: true },
    ]);

    let accumulated = '';
    cancelRef.current = sendChatStream(
      q, model,
      (token) => {
        accumulated += token;
        setMessages(prev => {
          const msgs = [...prev];
          const last = msgs[msgs.length - 1];
          if (last?.role === 'ai') msgs[msgs.length - 1] = { ...last, content: accumulated };
          return msgs;
        });
      },
      (data) => {
        cancelRef.current = null;
        setMessages(prev => {
          const msgs = [...prev];
          const last = msgs[msgs.length - 1];
          if (last?.role === 'ai') msgs[msgs.length - 1] = {
            ...last, streaming: false,
            duration_ms: data.duration_ms,
            ip_address: data.ip_address,
            cpu_percent: data.cpu_percent,
            memory_percent: data.memory_percent,
            created_at: data.created_at,
          };
          return msgs;
        });
        setHistory(prev => [{
          id: data.id, question: q, response: accumulated,
          model_name: model, duration_ms: data.duration_ms,
          ip_address: data.ip_address, cpu_percent: data.cpu_percent,
          memory_percent: data.memory_percent, created_at: data.created_at,
        }, ...prev]);
        setLoading(false);
      },
      (msg) => {
        cancelRef.current = null;
        setError(msg);
        setMessages(prev => prev.slice(0, -2));
        setLoading(false);
      },
      () => {
        // ユーザーによる中断 — 部分回答を残して streaming を解除
        cancelRef.current = null;
        setMessages(prev => {
          const msgs = [...prev];
          const last = msgs[msgs.length - 1];
          if (last?.role === 'ai') msgs[msgs.length - 1] = { ...last, streaming: false };
          return msgs;
        });
        setLoading(false);
      },
    );
  }, [input, loading, model]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && e.ctrlKey) { e.preventDefault(); handleSubmit(); }
  };

  const loadConversation = (conv: Conversation) => {
    setMessages([
      { role: 'user', content: conv.question },
      { role: 'ai', content: conv.response, duration_ms: conv.duration_ms, ip_address: conv.ip_address, created_at: conv.created_at },
    ]);
    setSidebarOpen(false);
  };

  return (
    <div className="flex flex-col h-dvh" style={{ background: 'var(--bg)' }}>

      {/* Header */}
      <header
        className="flex items-center gap-2 px-4 py-3 flex-shrink-0 border-b"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <h1 className="font-semibold text-base" style={{ color: 'var(--text)' }}>AI Chat</h1>

        <select
          value={model}
          onChange={e => setModel(e.target.value)}
          className="text-xs rounded-md px-2 py-1 border cursor-pointer outline-none"
          style={{ background: 'var(--surface2)', borderColor: 'var(--border)', color: 'var(--text)' }}
        >
          {models.map(m => <option key={m} value={m}>{m}</option>)}
        </select>

        <span className="text-xs px-2 py-0.5 rounded-full font-medium text-white" style={{ background: 'var(--accent)' }}>
          Ollama
        </span>

        {stats && (
          <div className="ml-auto flex items-center gap-3 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
            <span title="CPU使用率">CPU {stats.cpu_percent.toFixed(0)}%</span>
            <span title="メモリ使用率">MEM {stats.memory_used_gb}/{stats.memory_total_gb}GB</span>
          </div>
        )}

        <div className={`flex items-center gap-2 ${stats ? '' : 'ml-auto'}`}>
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg transition-colors"
            style={{ color: 'var(--text-muted)' }}
            title="テーマ切り替え"
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button
            onClick={() => setSidebarOpen(v => !v)}
            className="md:hidden p-2 rounded-lg transition-colors"
            style={{ color: 'var(--text-muted)' }}
            title="履歴"
          >
            <Menu size={18} />
          </button>
        </div>
      </header>


      {/* Main */}
      <div className="flex flex-1 overflow-hidden relative">

        {/* Chat area */}
        <div className="flex flex-col flex-1 overflow-hidden">
          <div ref={scrollContainerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full gap-3" style={{ color: 'var(--text-muted)' }}>
                <div className="text-5xl">💬</div>
                <p className="text-sm">質問を入力して送信してください</p>
                <p className="text-xs opacity-70">Enter で改行 / Ctrl+Enter で送信</p>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                <div className="text-xs font-medium px-1" style={{ color: 'var(--text-muted)' }}>
                  {msg.role === 'user' ? 'You' : 'AI'}
                </div>
                {msg.streaming && msg.content === '' ? (
                  <div className="thinking"><span /><span /><span /></div>
                ) : msg.role === 'user' ? (
                  <div className="bubble-user">{msg.content}</div>
                ) : (
                  <div className="bubble-ai md">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                )}
                {msg.role === 'ai' && !msg.streaming && msg.duration_ms && (
                  <div className="text-xs px-1 space-x-1" style={{ color: 'var(--text-muted)' }}>
                    <span>{msg.created_at && formatDate(msg.created_at)}</span>
                    <span>·</span>
                    <span>{(msg.duration_ms / 1000).toFixed(1)}sec</span>
                    {msg.cpu_percent != null && <><span>·</span><span>CPU {msg.cpu_percent}%</span></>}
                    {msg.memory_percent != null && <><span>·</span><span>MEM {msg.memory_percent}%</span></>}
                  </div>
                )}
              </div>
            ))}

            {error && (
              <div className="mx-auto text-sm px-4 py-2 rounded-lg border" style={{ background: 'rgba(239,68,68,0.1)', borderColor: '#ef4444', color: '#ef4444' }}>
                {error}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div
            className="px-4 py-3 border-t flex-shrink-0"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            <div className="flex gap-2 items-end max-w-3xl mx-auto">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => { setInput(e.target.value); adjustTextarea(); }}
                onKeyDown={handleKeyDown}
                placeholder="質問を入力... (Ctrl+Enter で送信)"
                disabled={loading}
                rows={1}
                className="flex-1 rounded-xl px-4 py-2.5 text-sm resize-none outline-none border transition-colors min-h-[44px] max-h-40"
                style={{
                  background: 'var(--surface2)', borderColor: 'var(--border)',
                  color: 'var(--text)',
                }}
              />
              {loading ? (
                <button
                  onClick={() => cancelRef.current?.()}
                  className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-semibold text-white transition-all flex-shrink-0 h-[44px]"
                  style={{ background: '#ef4444' }}
                  title="生成を停止"
                >
                  <AlertTriangle size={15} />
                  <span className="hidden sm:inline">停止</span>
                </button>
              ) : (
                <button
                  onClick={handleSubmit}
                  disabled={!input.trim()}
                  className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-semibold text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0 h-[44px]"
                  style={{ background: 'var(--accent)' }}
                >
                  <Send size={15} />
                  <span className="hidden sm:inline">送信</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar overlay (mobile) */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-40 md:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Sidebar */}
        <aside
          className={`
            fixed top-0 right-0 h-full z-50 w-72 flex flex-col border-l transition-transform duration-300
            md:relative md:translate-x-0 md:z-auto md:flex
            ${sidebarOpen ? 'translate-x-0' : 'translate-x-full md:translate-x-0'}
          `}
          style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
        >
          <div
            className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0"
            style={{ borderColor: 'var(--border)' }}
          >
            <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              履歴 ({history.length})
            </span>
            <button
              onClick={() => setSidebarOpen(false)}
              className="md:hidden p-1 rounded"
              style={{ color: 'var(--text-muted)' }}
            >
              <X size={16} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {history.map(conv => (
              <button
                key={conv.id}
                onClick={() => loadConversation(conv)}
                className="w-full text-left px-3 py-2.5 rounded-lg transition-colors border border-transparent hover:border-[var(--border)] text-sm"
                style={{ color: 'var(--text)' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface2)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div className="truncate font-medium text-xs">{conv.question}</div>
                <div className="text-xs mt-0.5 space-x-1" style={{ color: 'var(--text-muted)' }}>
                  <span>{formatDate(conv.created_at)}</span>
                  <span>· {conv.model_name}</span>
                  {conv.ip_address && <span>· {conv.ip_address}</span>}
                </div>
              </button>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
