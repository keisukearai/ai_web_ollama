import json
import queue
from queue import Empty
import threading
import time
import psutil
import requests
from django.conf import settings
from django.http import StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Conversation
from .serializers import ConversationSerializer

# psutil の cpu_percent は初回呼び出しが 0.0 を返すため、起動時に捨て呼び
psutil.cpu_percent(interval=None)


@method_decorator(csrf_exempt, name='dispatch')
class StreamChatView(View):
    def post(self, request):
        body = json.loads(request.body)
        question = body.get('question', '').strip()
        model = body.get('model', settings.OLLAMA_MODEL)
        timeout_sec = int(body.get('timeout', 120))

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

            def fetch_ollama():
                full_response = ''
                start = time.time()
                peak_cpu = 0.0
                peak_memory = 0.0
                token_count = 0

                # /api/chat を使用（qwen3 の think: false が正しく効く）
                payload = {
                    'model': model,
                    'messages': [{'role': 'user', 'content': question}],
                    'stream': True,
                }
                if model.startswith('qwen3'):
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
                            )
                            token_queue.put(('done', {
                                'done': True, 'id': conv.id,
                                'created_at': conv.created_at.isoformat(),
                                'duration_ms': duration_ms,
                                'ip_address': ip_address,
                                'cpu_percent': conv.cpu_percent,
                                'memory_percent': conv.memory_percent,
                            }))
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
                        # キュータイムアウト（thinking が長すぎる等）→ Ollama を停止してエラー返却
                        stop_event.set()
                        if response_holder[0] is not None:
                            try:
                                response_holder[0].close()
                            except Exception:
                                pass
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
