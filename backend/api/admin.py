from django.contrib import admin
from .models import Conversation


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'question_preview', 'model_name', 'duration_sec', 'created_at']
    list_filter = ['model_name', 'created_at']
    search_fields = ['question', 'response']
    readonly_fields = ['question', 'response', 'model_name', 'duration_ms', 'created_at']
    ordering = ['-created_at']
    list_per_page = 50

    def question_preview(self, obj):
        return obj.question[:80] + ('…' if len(obj.question) > 80 else '')
    question_preview.short_description = '質問内容'

    def duration_sec(self, obj):
        if obj.duration_ms is None:
            return '-'
        return f'{obj.duration_ms / 1000:.1f}秒'
    duration_sec.short_description = '応答時間'
