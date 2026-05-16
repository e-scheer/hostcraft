from __future__ import annotations

from rest_framework import serializers

from .models import Allocation, NetworkProfile


class NetworkProfileSerializer(serializers.ModelSerializer):
    # Never echo the agent key back to the client.
    playit_agent_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_playit_agent_key = serializers.SerializerMethodField()

    class Meta:
        model = NetworkProfile
        fields = [
            "mode",
            "custom_domain",
            "playit_hostname",
            "playit_agent_key",
            "has_playit_agent_key",
            "public_ip_override",
            "updated_at",
        ]

    def get_has_playit_agent_key(self, obj: NetworkProfile) -> bool:
        return bool(obj.playit_agent_key)

    def update(self, instance: NetworkProfile, validated_data: dict) -> NetworkProfile:
        # PATCH with an empty agent key shouldn't wipe the existing one.
        if not validated_data.get("playit_agent_key"):
            validated_data.pop("playit_agent_key", None)
        return super().update(instance, validated_data)


class AllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Allocation
        fields = [
            "id",
            "label",
            "host_port",
            "container_port",
            "protocol",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_host_port(self, value: int) -> int:
        if not (1 <= value <= 65535):
            raise serializers.ValidationError("Port must be between 1 and 65535.")
        return value

    def validate_container_port(self, value: int) -> int:
        if not (1 <= value <= 65535):
            raise serializers.ValidationError("Port must be between 1 and 65535.")
        return value
