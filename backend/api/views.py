import json
import time
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

        def generate():
            full_response = ''
            start = time.time()
            try:
                with requests.post(
                    f"{settings.OLLAMA_URL}/api/generate",
                    json={'model': model, 'prompt': question, 'stream': True},
                    stream=True,
                    timeout=300,
                ) as resp:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        data = json.loads(line)
                        token = data.get('response', '')
                        if token:
                            full_response += token
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if data.get('done'):
                            duration_ms = int((time.time() - start) * 1000)
                            conv = Conversation.objects.create(
                                question=question,
                                response=full_response,
                                model_name=model,
                                duration_ms=duration_ms,
                            )
                            yield f"data: {json.dumps({'done': True, 'id': conv.id, 'created_at': conv.created_at.isoformat(), 'duration_ms': duration_ms})}\n\n"
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
