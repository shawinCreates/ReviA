from __future__ import annotations

from api.auth import SupabasePrincipal
from api.models import Profile


def get_or_create_profile(principal: SupabasePrincipal) -> Profile:
    profile, created = Profile.objects.get_or_create(
        id=principal.id,
        defaults={"email": principal.email},
    )

    if not created and principal.email and not profile.email:
        profile.email = principal.email
        profile.save(update_fields=["email", "updated_at"])

    return profile
