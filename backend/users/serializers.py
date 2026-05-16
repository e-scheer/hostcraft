from __future__ import annotations

from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "is_staff", "date_joined"]
        read_only_fields = fields
