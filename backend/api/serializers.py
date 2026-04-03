from rest_framework import serializers
from .models import Conversation


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ['id', 'question', 'response', 'model_name', 'duration_ms', 'ip_address', 'created_at']
        read_only_fields = ['id', 'created_at']
