from django.urls import path

from core.auth import AuthStatusView, LoginView, LogoutView
from core.views import (
    HealthView,
    NotificationPreferencesView,
    PlatformConfigView,
    PlatformStatusView,
    ScheduledTaskDetailView,
    ScheduledTaskListView,
    ScheduledTaskPauseView,
    ScheduledTaskResumeView,
    ScheduledTaskTriggerView,
    SchedulerStatusView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/status/", AuthStatusView.as_view(), name="auth-status"),
    path("platform/status/", PlatformStatusView.as_view(), name="platform-status"),
    path("platform/config/", PlatformConfigView.as_view(), name="platform-config"),
    path(
        "notifications/<int:portfolio_id>/preferences/",
        NotificationPreferencesView.as_view(),
        name="notification-prefs",
    ),
    # Scheduler
    path("scheduler/status/", SchedulerStatusView.as_view(), name="scheduler-status"),
    path("scheduler/tasks/", ScheduledTaskListView.as_view(), name="scheduler-task-list"),
    path(
        "scheduler/tasks/<str:task_id>/",
        ScheduledTaskDetailView.as_view(),
        name="scheduler-task-detail",
    ),
    path(
        "scheduler/tasks/<str:task_id>/pause/",
        ScheduledTaskPauseView.as_view(),
        name="scheduler-task-pause",
    ),
    path(
        "scheduler/tasks/<str:task_id>/resume/",
        ScheduledTaskResumeView.as_view(),
        name="scheduler-task-resume",
    ),
    path(
        "scheduler/tasks/<str:task_id>/trigger/",
        ScheduledTaskTriggerView.as_view(),
        name="scheduler-task-trigger",
    ),
]
