from __future__ import annotations

from api.views import HealthView
from django.urls import include, path

urlpatterns = [
    path("api/v1/health", HealthView.as_view(), name="health"),
    path("api/v1/", include("api.urls")),
]
