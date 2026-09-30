from __future__ import annotations

from rest_framework import serializers

from api.models import Profile


class ProfileSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Profile
        fields = ["id", "email", "display_name", "max_documents", "created_at"]
        read_only_fields = fields
