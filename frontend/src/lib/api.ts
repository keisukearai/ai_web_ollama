export type Conversation = {
  id: number;
  question: string;
  response: string;
  model_name: string;
  duration_ms: number | null;
  created_at: string;
};

const BASE = '/api';

export async function sendChatStream(
  question: string,
  model: string,
  onToken: (token: string) => void,
  onDone: (data: { id: number; created_at: string; duration_ms: number }) => void,
  onError: (msg: string) => void,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/chat/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, model }),
    });
  } catch (e) {
    onError('サーバーに接続できませんでした');
    return;
  }

  if (!res.ok || !res.body) {
    onError(`エラー: ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (data.error) { onError(data.error); return; }
        if (data.token) onToken(data.token);
        if (data.done) onDone(data);
      } catch {}
    }
  }
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
