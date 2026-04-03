import json
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

        if not question:
            def error_stream():
                yield f"data: {json.dumps({'error': '質問を入力してください'})}\n\n"
            return StreamingHttpResponse(error_stream(), content_type='text/event-stream')

        # X-Forwarded-For（nginxプロキシ経由）対応
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = forwarded_for.split(',')[0].strip() if forwarded_for else request.META.get('REMOTE_ADDR')

        def generate():
            full_response = ''
            start = time.time()
            peak_cpu = 0.0
            peak_memory = 0.0
            token_count = 0
            try:
                with requests.post(
                    f"{settings.OLLAMA_URL}/api/generate",
                    json={'model': model, 'prompt': question, 'stream': True},
                    stream=True,
                    timeout=120,
                ) as resp:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        data = json.loads(line)
                        token = data.get('response', '')
                        if token:
                            full_response += token
                            token_count += 1
                            # 10トークンごとにサンプリング
                            if token_count % 10 == 0:
                                cpu = psutil.cpu_percent(interval=None)
                                mem = psutil.virtual_memory().percent
                                if cpu > peak_cpu:
                                    peak_cpu = cpu
                                if mem > peak_memory:
                                    peak_memory = mem
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if data.get('done'):
                            # 最終サンプリング
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
                            yield f"data: {json.dumps({'done': True, 'id': conv.id, 'created_at': conv.created_at.isoformat(), 'duration_ms': duration_ms, 'ip_address': ip_address, 'cpu_percent': conv.cpu_percent, 'memory_percent': conv.memory_percent})}\n\n"
                            return
            except requests.exceptions.Timeout:
                yield f"data: {json.dumps({'error': 'AIの応答がタイムアウトしました'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': f'Ollama接続エラー: {e}'})}\n\n"

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
