export type Conversation = {
  id: number;
  question: string;
  response: string;
  model_name: string;
  duration_ms: number | null;
  created_at: string;
};

const BASE = '/api';

export async function sendChat(question: string, model?: string): Promise<Conversation> {
  const res = await fetch(`${BASE}/chat/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, model }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `エラー: ${res.status}`);
  }
  return res.json();
}

export async function fetchHistory(limit = 50): Promise<Conversation[]> {
  const res = await fetch(`${BASE}/history/?limit=${limit}`);
  if (!res.ok) throw new Error('履歴の取得に失敗しました');
  return res.json();
}

export async function fetchModels(): Promise<string[]> {
  const res = await fetch(`${BASE}/models/`);
  if (!res.ok) return ['gemma3:4b'];
  const data = await res.json();
  return data.models ?? ['gemma3:4b'];
}
