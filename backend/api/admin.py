from django.contrib import admin
from django.utils.html import format_html
from .models import Conversation, AppConfig


@admin.register(AppConfig)
class AppConfigAdmin(admin.ModelAdmin):
    list_display = ['key', 'value_display', 'description', 'updated_at']
    search_fields = ['key', 'description']
    readonly_fields = ['updated_at']

    def value_display(self, obj):
        if obj.value.startswith('http://') or obj.value.startswith('https://'):
            return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', obj.value, obj.value)
        return obj.value
    value_display.short_description = '値'


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'question_preview', 'model_name', 'mode', 'duration_sec', 'cpu_display', 'memory_display', 'ip_address', 'timeout_setting_display', 'status_display', 'created_at']
    list_filter = ['model_name', 'mode', 'timed_out', 'user_aborted', 'ip_address', 'created_at']
    search_fields = ['question', 'response']
    readonly_fields = ['question', 'response', 'model_name', 'mode', 'duration_ms', 'ip_address', 'cpu_percent', 'memory_percent', 'timed_out', 'user_aborted', 'timeout_setting_sec', 'created_at']
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

    def timeout_setting_display(self, obj):
        if obj.timeout_setting_sec is None:
            return '-'
        return f'{obj.timeout_setting_sec}秒'
    timeout_setting_display.short_description = '設定時間'

    def status_display(self, obj):
        from django.utils.html import format_html
        if obj.timed_out:
            return format_html('<span style="color:#dc2626;font-weight:bold;">✗</span>')
        if obj.user_aborted:
            return format_html('<span style="color:#ea580c;font-weight:bold;">!</span>')
        return ''
    status_display.short_description = 'ステータス'
