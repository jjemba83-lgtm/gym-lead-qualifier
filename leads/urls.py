"""
URL configuration for leads app.
"""
from django.urls import path
from .views import dashboard as dashboard_views
from .views import actions as action_views

urlpatterns = [
    # Dashboard views
    path('dashboard/', dashboard_views.dashboard, name='dashboard'),
    path('dashboard/pending/<int:pending_id>/', dashboard_views.pending_detail, name='pending_detail'),
    path('dashboard/conversations/', dashboard_views.conversations_list, name='conversations_list'),
    path('dashboard/conversation/<int:conversation_id>/', dashboard_views.conversation_detail, name='conversation_detail'),
    
    # Action views
    path('actions/check-email/', action_views.check_email_now, name='check_email_now'),
    path('actions/approve/<int:pending_id>/', action_views.approve_response, name='approve_response'),
    path('actions/edit/<int:pending_id>/', action_views.edit_response, name='edit_response'),
    path('actions/reject/<int:pending_id>/', action_views.reject_response, name='reject_response'),
    path('actions/mark-complete/<int:conversation_id>/', action_views.mark_complete, name='mark_complete'),
]
