export type Conversation = {
  id: number;
  question: string;
  response: string;
  model_name: string;
  duration_ms: number | null;
  ip_address: string | null;
  cpu_percent: number | null;
  memory_percent: number | null;
  created_at: string;
};

export type ServerStats = {
  cpu_percent: number;
  memory_percent: number;
  memory_used_gb: number;
  memory_total_gb: number;
};

const BASE = '/api';

export async function sendChatStream(
  question: string,
  model: string,
  onToken: (token: string) => void,
  onDone: (data: { id: number; created_at: string; duration_ms: number; ip_address: string | null; cpu_percent: number | null; memory_percent: number | null }) => void,
  onError: (msg: string) => void,
): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120_000);

  let res: Response;
  try {
    res = await fetch(`${BASE}/chat/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, model }),
      signal: controller.signal,
    });
  } catch (e: unknown) {
    clearTimeout(timeoutId);
    if (e instanceof DOMException && e.name === 'AbortError') {
      onError('タイムアウト：応答に時間がかかりすぎました。質問を短くして再送してください。');
    } else {
      onError('サーバーに接続できませんでした');
    }
    return;
  }

  if (!res.ok || !res.body) {
    clearTimeout(timeoutId);
    onError(`エラー: ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
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
          if (data.error) { clearTimeout(timeoutId); onError(data.error); return; }
          if (data.token) onToken(data.token);
          if (data.done) { clearTimeout(timeoutId); onDone(data); }
        } catch {}
      }
    }
  } catch (e: unknown) {
    clearTimeout(timeoutId);
    if (e instanceof DOMException && e.name === 'AbortError') {
      onError('タイムアウト：応答に時間がかかりすぎました。質問を短くして再送してください。');
    } else {
      onError('接続が切断されました');
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

export async function fetchStats(): Promise<ServerStats | null> {
  try {
    const res = await fetch(`${BASE}/stats/`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
