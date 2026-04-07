from django.contrib import admin
from .models import Conversation


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'question_preview', 'model_name', 'duration_sec', 'cpu_display', 'memory_display', 'ip_address', 'timed_out_display', 'created_at']
    list_filter = ['model_name', 'timed_out', 'ip_address', 'created_at']
    search_fields = ['question', 'response']
    readonly_fields = ['question', 'response', 'model_name', 'duration_ms', 'ip_address', 'cpu_percent', 'memory_percent', 'timed_out', 'created_at']
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

    def cpu_display(self, obj):
        if obj.cpu_percent is None:
            return '-'
        return f'{obj.cpu_percent}%'
    cpu_display.short_description = 'CPU(ピーク)'

    def memory_display(self, obj):
        if obj.memory_percent is None:
            return '-'
        return f'{obj.memory_percent}%'
    memory_display.short_description = 'MEM(ピーク)'

    def timed_out_display(self, obj):
        return '⚠ タイムアウト' if obj.timed_out else '-'
    timed_out_display.short_description = 'タイムアウト'
