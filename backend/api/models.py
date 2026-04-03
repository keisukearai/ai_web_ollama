from django.db import models


class Conversation(models.Model):
    question = models.TextField()
    response = models.TextField()
    model_name = models.CharField(max_length=100, default='gemma3:4b')
    duration_ms = models.IntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    cpu_percent = models.FloatField(null=True, blank=True)
    memory_percent = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} - {self.question[:50]}"
