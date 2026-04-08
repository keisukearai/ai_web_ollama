import json
import os
import queue
from queue import Empty
import threading
import time
import psutil
import requests
from django.conf import settings
from django.http import StreamingHttpResponse
from django.utils.timezone import localtime
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Conversation, AppConfig
from .serializers import ConversationSerializer

# psutil の cpu_percent は初回呼び出しが 0.0 を返すため、起動時に捨て呼び
psutil.cpu_percent(interval=None)

CREDENTIALS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'credentials', 'google_sheets.json')

FAQ_MODEL_NAME = 'qwen2.5-techbridge'
FAQ_BASE_MODEL = 'qwen2.5:1.5b'
EMBED_MODEL = 'nomic-embed-text'
FAQ_TOP_K = 5


def _cosine_similarity(a, b):
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _get_faq_context(question: str) -> str:
    """質問をベクトル化し、類似FAQ上位K件でシステムプロンプトを構築する"""
    import json
    from .models import FAQ, AppConfig

    # 質問をベクトル化
    resp = requests.post(
        f"{settings.OLLAMA_URL}/api/embed",
        json={'model': EMBED_MODEL, 'input': question},
        timeout=15,
    )
    resp.raise_for_status()
    q_vec = resp.json()['embeddings'][0]

    # 全FAQとコサイン類似度を計算
    faqs = list(FAQ.objects.exclude(embedding=''))
    scores = []
    for faq in faqs:
        faq_vec = json.loads(faq.embedding)
        score = _cosine_similarity(q_vec, faq_vec)
        scores.append((score, faq))

    scores.sort(key=lambda x: x[0], reverse=True)
    top_faqs = [faq for _, faq in scores[:FAQ_TOP_K]]

    # システムプロンプト組み立て（AppConfigから取得）
    header = AppConfig.objects.filter(key='faq_system_prompt_header').values_list('value', flat=True).first() or \
        'あなたは株式会社テックブリッジの社内アシスタントAIです。以下のFAQを参考に回答してください。\n\n'
    footer = AppConfig.objects.filter(key='faq_system_prompt_footer').values_list('value', flat=True).first() or \
        '\n回答は簡潔かつ丁寧にしてください。'

    faq_text = '\n'.join(f'Q: {f.question}\nA: {f.answer}' for f in top_faqs)
    return header + faq_text + footer


def _get_spreadsheet_id():
    url = AppConfig.objects.filter(key='spreadsheet_url').values_list('value', flat=True).first()
    if not url:
        return None
    # URL から ID を抽出: /spreadsheets/d/{ID}/
    import re
    m = re.search(r'/spreadsheets/d/([^/]+)', url)
    return m.group(1) if m else None

def _append_to_sheet(row: list):
    """スプレッドシートに1行追記（失敗しても例外を外に出さない）"""
    try:
        spreadsheet_id = _get_spreadsheet_id()
        if not spreadsheet_id:
            return
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(spreadsheet_id)
        sh.sheet1.append_row(row, value_input_option='USER_ENTERED')
    except Exception:
        pass


@method_decorator(csrf_exempt, name='dispatch')
class StreamChatView(View):
    def post(self, request):
        body = json.loads(request.body)
        question = body.get('question', '').strip()
        model = body.get('model', settings.OLLAMA_MODEL)
        timeout_sec = int(body.get('timeout', 120))
        mode = body.get('mode', '通常')
        history = body.get('history', [])[-10:]  # 最大10メッセージ

        SYSTEM_MESSAGES = {
            '要約': '回答は簡潔にまとめ、100〜150文字程度で答えてください。',
            '深く': '詳しく、多角的な視点から丁寧に説明してください。',
        }

        # qwen2.5-techbridge はベクトル検索でFAQコンテキストを注入
        actual_model = model
        faq_system_prompt = None
        if model == FAQ_MODEL_NAME:
            actual_model = FAQ_BASE_MODEL
            try:
                faq_system_prompt = _get_faq_context(question)
            except Exception as e:
                faq_system_prompt = None

        if not question:
            def error_stream():
                yield f"data: {json.dumps({'error': '質問を入力してください'})}\n\n"
            return StreamingHttpResponse(error_stream(), content_type='text/event-stream')

        # X-Forwarded-For（nginxプロキシ経由）対応
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = forwarded_for.split(',')[0].strip() if forwarded_for else request.META.get('REMOTE_ADDR')

        def generate():
            token_queue = queue.Queue()
            stop_event = threading.Event()
            response_holder = [None]  # iter_lines() を外部から close() するための参照
            full_response_holder = ['']
            start_holder = [time.time()]

            def fetch_ollama():
                full_response = ''
                start = start_holder[0]
                peak_cpu = 0.0
                peak_memory = 0.0
                token_count = 0

                # /api/chat を使用（qwen3 の think: false が正しく効く）
                messages = []
                if faq_system_prompt:
                    messages.append({'role': 'system', 'content': faq_system_prompt})
                elif mode in SYSTEM_MESSAGES:
                    messages.append({'role': 'system', 'content': SYSTEM_MESSAGES[mode]})
                for h in history:
                    role = 'assistant' if h.get('role') == 'ai' else 'user'
                    content = h.get('content', '').strip()
                    if content:
                        messages.append({'role': role, 'content': content})
                messages.append({'role': 'user', 'content': question})

                payload = {
                    'model': actual_model,
                    'messages': messages,
                    'stream': True,
                }
                if actual_model.startswith('qwen3'):
                    payload['think'] = False

                try:
                    resp = requests.post(
                        f"{settings.OLLAMA_URL}/api/chat",
                        json=payload,
                        stream=True,
                        timeout=timeout_sec,
                    )
                    response_holder[0] = resp

                    for line in resp.iter_lines():
                        if stop_event.is_set():
                            break
                        if not line:
                            continue
                        data = json.loads(line)
                        token = data.get('message', {}).get('content', '')
                        if token:
                            full_response += token
                            full_response_holder[0] = full_response
                            token_count += 1
                            if token_count % 10 == 0:
                                cpu = psutil.cpu_percent(interval=None)
                                mem = psutil.virtual_memory().percent
                                if cpu > peak_cpu:
                                    peak_cpu = cpu
                                if mem > peak_memory:
                                    peak_memory = mem
                            token_queue.put(('token', token))
                        if data.get('done'):
                            cpu = psutil.cpu_percent(interval=None)
                            mem = psutil.virtual_memory().percent
                            if cpu > peak_cpu:
                                peak_cpu = cpu
                            if mem > peak_memory:
                                peak_memory = mem
                            duration_ms = int((time.time() - start) * 1000)
                            conv = Conversation.objects.create(
                                question=question,
                                response=full_response,
                                model_name=model,
                                duration_ms=duration_ms,
                                ip_address=ip_address,
                                cpu_percent=round(peak_cpu, 1),
                                memory_percent=round(peak_memory, 1),
                                timeout_setting_sec=timeout_sec,
                                mode=mode,
                            )
                            token_queue.put(('done', {
                                'done': True, 'id': conv.id,
                                'created_at': conv.created_at.isoformat(),
                                'duration_ms': duration_ms,
                                'ip_address': ip_address,
                                'cpu_percent': conv.cpu_percent,
                                'memory_percent': conv.memory_percent,
                            }))
                            # スプレッドシートに非同期で追記
                            threading.Thread(target=_append_to_sheet, args=([
                                localtime(conv.created_at).strftime('%Y-%m-%d %H:%M:%S'),
                                question,
                                full_response,
                                model,
                                mode,
                                f'{duration_ms / 1000:.1f}',
                                '完了',
                            ],), daemon=True).start()
                            return
                except requests.exceptions.Timeout:
                    token_queue.put(('error', 'AIの応答がタイムアウトしました'))
                except Exception as e:
                    if not stop_event.is_set():
                        token_queue.put(('error', f'Ollama接続エラー: {e}'))
                finally:
                    token_queue.put(None)

            thread = threading.Thread(target=fetch_ollama, daemon=True)
            thread.start()

            try:
                while True:
                    try:
                        item = token_queue.get(timeout=timeout_sec + 5)
                    except Empty:
                        # キュータイムアウト → Ollama を停止して部分レスポンスを保存
                        stop_event.set()
                        if response_holder[0] is not None:
                            try:
                                response_holder[0].close()
                            except Exception:
                                pass
                        duration_ms = int((time.time() - start_holder[0]) * 1000)
                        Conversation.objects.create(
                            question=question,
                            response=full_response_holder[0],
                            model_name=model,
                            duration_ms=duration_ms,
                            ip_address=ip_address,
                            cpu_percent=None,
                            memory_percent=None,
                            timed_out=True,
                            timeout_setting_sec=timeout_sec,
                            mode=mode,
                        )
                        yield f"data: {json.dumps({'error': 'タイムアウト：応答に時間がかかりすぎました'})}\n\n"
                        break
                    if item is None:
                        break
                    kind, data = item
                    if kind == 'token':
                        yield f"data: {json.dumps({'token': data})}\n\n"
                    elif kind == 'done':
                        yield f"data: {json.dumps(data)}\n\n"
                        break
                    elif kind == 'error':
                        yield f"data: {json.dumps({'error': data})}\n\n"
                        break
            except GeneratorExit:
                # クライアント切断 → stop_event + resp.close() で Ollama を即時停止
                stop_event.set()
                if response_holder[0] is not None:
                    try:
                        response_holder[0].close()
                    except Exception:
                        pass
                # 経過時間で手動停止とタイムアウトを判定して DB 保存
                elapsed = time.time() - start_holder[0]
                if full_response_holder[0]:
                    try:
                        is_timeout = elapsed >= timeout_sec - 5
                        Conversation.objects.create(
                            question=question,
                            response=full_response_holder[0],
                            model_name=model,
                            duration_ms=int(elapsed * 1000),
                            ip_address=ip_address,
                            cpu_percent=None,
                            memory_percent=None,
                            timed_out=is_timeout,
                            user_aborted=not is_timeout,
                            timeout_setting_sec=timeout_sec,
                            mode=mode,
                        )
                    except Exception:
                        pass

        response = StreamingHttpResponse(generate(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


class HistoryView(APIView):
    def get(self, request):
        limit = min(int(request.query_params.get('limit', 50)), 200)
        convs = Conversation.objects.all()[:limit]
        return Response(ConversationSerializer(convs, many=True).data)


class ModelListView(APIView):
    def get(self, request):
        try:
            resp = requests.get(f"{settings.OLLAMA_URL}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m['name'] for m in resp.json().get('models', [])]
        except Exception:
            models = [settings.OLLAMA_MODEL]
        # qwen2.5-techbridge はollamamodel不要のため常に先頭に注入
        models = [m for m in models if m != FAQ_MODEL_NAME]
        models.insert(0, FAQ_MODEL_NAME)
        return Response({'models': models})


class StatsView(APIView):
    def get(self, request):
        mem = psutil.virtual_memory()
        return Response({
            'cpu_percent': psutil.cpu_percent(interval=None),
            'memory_percent': mem.percent,
            'memory_used_gb': round(mem.used / 1024 ** 3, 1),
            'memory_total_gb': round(mem.total / 1024 ** 3, 1),
        })
