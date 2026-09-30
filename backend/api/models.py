"""Application data models.

Identity lives in `supabase.auth.users`. `Profile` is a local mirror keyed by
that id: it exists so the rest of the app has a row to hang application state
off (display name, quota) without re-implementing authentication. The id is the
Supabase user id, so there is never a mapping to keep in sync.
"""

from __future__ import annotations

from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Profile(TimestampedModel):
    """One row per Supabase user, created on first authenticated request."""

    id = models.UUIDField(primary_key=True, editable=False)
    email = models.EmailField(null=True, blank=True)
    display_name = models.CharField(max_length=120, blank=True)

    # Per-user allowance on stored documents. A value of 0 means "unlimited",
    # which is the right default for local development and the wrong one for
    # production, so it is explicit rather than implied by a null.
    max_documents = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "profiles"
        verbose_name = "profile"
        verbose_name_plural = "profiles"

    def __str__(self) -> str:
        return self.display_name or self.email or str(self.id)
