from django.urls import path

from . import views

urlpatterns = [
    path('ai-chat/credential/', views.credential_view, name='ai_chat_credential'),
    path('ai-chat/models/', views.models_view, name='ai_chat_models'),
    path('ai-chat/projects/', views.projects_view, name='ai_chat_projects'),
    path('ai-chat/projects/<int:project_id>/', views.delete_project_view, name='ai_chat_delete_project'),
    path(
        'ai-chat/projects/<int:project_id>/messages/',
        views.clear_project_history_view, name='ai_chat_clear_history',
    ),
    path('ai-chat/projects/<int:project_id>/tabs/<str:tab_key>/', views.tab_view, name='ai_chat_tab'),
    path(
        'ai-chat/projects/<int:project_id>/tabs/<str:tab_key>/messages/',
        views.send_message_view, name='ai_chat_send_message',
    ),
    path('ai-chat/bundles/<int:bundle_id>/download/', views.download_bundle_view, name='ai_chat_download_bundle'),
    path('ai-chat/messages/<int:message_id>/', views.message_detail_view, name='ai_chat_message_detail'),
]
