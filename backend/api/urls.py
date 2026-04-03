from django.urls import path
from . import views

urlpatterns = [
    path('chat/', views.ChatView.as_view(), name='chat'),
    path('history/', views.HistoryView.as_view(), name='history'),
    path('models/', views.ModelListView.as_view(), name='models'),
]
