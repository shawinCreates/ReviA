from __future__ import annotations

from django.urls import include, path

from api.views import HealthView

urlpatterns = [
    path("health", HealthView.as_view(), name="health-ping"),
    path("api/v1/health", HealthView.as_view(), name="health"),
    path("api/v1/", include("api.urls")),
]
