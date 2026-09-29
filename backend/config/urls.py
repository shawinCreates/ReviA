"""
Root URL configuration.

The API is mounted at /api/. Everything except /api/health requires a verified
Supabase JWT; see api/middleware.py.

`/admin/` is intentionally absent. Supabase owns auth and there is no Django
user model, so the admin site would be unreachable. See decisions.md D-004.
"""

from django.http import HttpResponseNotFound, JsonResponse
from django.urls import include, path

from api.errors import error_payload

urlpatterns = [
    path("api/", include("api.urls")),
]


def api_not_found(request, exception):
    """
    An unmatched /api/ path returns the error envelope, not an HTML 404 page.

    Without this, a typo in a path skips DRF entirely — there is no view to
    raise from — and Django serves its own 404. The frontend's single error
    path does `response.json()`, so it would see unparseable HTML and report a
    generic failure instead of "no such endpoint". The contract in api.md says
    every error response is the envelope; this is what enforces it.

    Only /api/ is affected. Anything else keeps Django's normal handling, since
    a browser hitting an unknown page wants HTML, not JSON.
    """
    if request.path.startswith("/api/"):
        return JsonResponse(
            error_payload("not_found", "No such endpoint."), status=404
        )
    return HttpResponseNotFound("Not found")


def api_server_error(request):
    """The 500 equivalent: keep the envelope shape for API paths."""
    if request.path.startswith("/api/"):
        return JsonResponse(
            error_payload("server_error", "Something went wrong."), status=500
        )
    return HttpResponseNotFound("Not found")


handler404 = api_not_found
handler500 = api_server_error
