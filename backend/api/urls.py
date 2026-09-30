from __future__ import annotations

from django.urls import path

from api.views import DemoPrincipalView, MeView

urlpatterns = [
    path("me", MeView.as_view(), name="me"),
    path("session", DemoPrincipalView.as_view(), name="session"),
]
