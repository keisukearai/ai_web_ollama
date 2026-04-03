import time
import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Conversation
from .serializers import ConversationSerializer


class ChatView(APIView):
    def post(self, request):
        question = request.data.get('question', '').strip()
        if not question:
            return Response({'error': '質問を入力してください'}, status=400)

        model = request.data.get('model', settings.OLLAMA_MODEL)
        ollama_url = f"{settings.OLLAMA_URL}/api/generate"

        start = time.time()
        try:
            resp = requests.post(
                ollama_url,
                json={'model': model, 'prompt': question, 'stream': False},
                timeout=300,
            )
            resp.raise_for_status()
            response_text = resp.json().get('response', '')
        except requests.exceptions.Timeout:
            return Response({'error': 'AIの応答がタイムアウトしました'}, status=504)
        except Exception as e:
            return Response({'error': f'Ollama接続エラー: {e}'}, status=502)

        duration_ms = int((time.time() - start) * 1000)

        conv = Conversation.objects.create(
            question=question,
            response=response_text,
            model_name=model,
            duration_ms=duration_ms,
        )
        return Response(ConversationSerializer(conv).data, status=201)


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
