from django.db import models


class Conversation(models.Model):
    question = models.TextField()
    response = models.TextField()
    model_name = models.CharField(max_length=100, default='gemma3:4b')
    duration_ms = models.IntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    cpu_percent = models.FloatField(null=True, blank=True)
    memory_percent = models.FloatField(null=True, blank=True)
    mode = models.CharField(max_length=10, default='通常')
    timed_out = models.BooleanField(default=False)
    user_aborted = models.BooleanField(default=False)
    timeout_setting_sec = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} - {self.question[:50]}"


class SpreadsheetLink(models.Model):
    class Meta:
        managed = False
        verbose_name = 'スプレッドシート'
        verbose_name_plural = 'スプレッドシート'


class FAQ(models.Model):
    category = models.CharField(max_length=100, verbose_name='カテゴリ')
    question = models.TextField(verbose_name='質問')
    answer = models.TextField(verbose_name='回答')
    row_number = models.IntegerField(verbose_name='スプシ行番号')

    class Meta:
        ordering = ['row_number']
        verbose_name = 'FAQ'
        verbose_name_plural = 'FAQ'

    def __str__(self):
        return f"[{self.category}] {self.question[:50]}"


class AppConfig(models.Model):
    key = models.CharField(max_length=100, unique=True, verbose_name='キー')
    value = models.TextField(verbose_name='値')
    description = models.CharField(max_length=200, blank=True, verbose_name='説明')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新日時')

    class Meta:
        verbose_name = '設定'
        verbose_name_plural = '設定'

    def __str__(self):
        return self.key
