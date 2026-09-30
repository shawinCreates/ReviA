"""Resolving an authenticated caller to a Profile.

Kept out of the authentication class on purpose. DRF authenticators are called
on every request and should not write to the database; a side effect there would
mean a read-only endpoint could fail because of a write.
"""

from __future__ import annotations

from api.auth import SupabasePrincipal
from api.models import Profile


def get_or_create_profile(principal: SupabasePrincipal) -> Profile:
    """Return the caller's Profile, creating it on first sight.

    Uses get_or_create rather than update_or_create so a concurrent first
    request cannot clobber a display name the user has since set.
    """
    profile, created = Profile.objects.get_or_create(
        id=principal.id,
        defaults={"email": principal.email},
    )

    # Backfill an email that arrived after the row was first created. Only fills
    # a gap; never overwrites a value we already hold.
    if not created and principal.email and not profile.email:
        profile.email = principal.email
        profile.save(update_fields=["email", "updated_at"])

    return profile
