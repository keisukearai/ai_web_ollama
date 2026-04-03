from django.urls import path
from . import views

urlpatterns = [
    path('chat/', views.StreamChatView.as_view(), name='chat'),
    path('history/', views.HistoryView.as_view(), name='history'),
    path('models/', views.ModelListView.as_view(), name='models'),
    path('stats/', views.StatsView.as_view(), name='stats'),
]
