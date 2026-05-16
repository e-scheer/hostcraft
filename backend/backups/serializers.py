from __future__ import annotations

from rest_framework import serializers

from .models import Backup, BackupDestination


class BackupDestinationSerializer(serializers.ModelSerializer):
    # Never echo the secret back to the client.
    secret_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_secret = serializers.SerializerMethodField()

    class Meta:
        model = BackupDestination
        fields = [
            "id",
            "name",
            "kind",
            "endpoint_url",
            "bucket",
            "prefix",
            "region",
            "access_key",
            "secret_key",
            "has_secret",
            "auto_upload",
            "enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_has_secret(self, obj: BackupDestination) -> bool:
        return bool(obj.secret_key)

    def update(self, instance: BackupDestination, validated_data: dict) -> BackupDestination:
        # PATCH with empty secret_key shouldn't blank an existing secret —
        # treat blank/missing as "keep the current one".
        if not validated_data.get("secret_key"):
            validated_data.pop("secret_key", None)
        return super().update(instance, validated_data)


class BackupSerializer(serializers.ModelSerializer):
    remote_destination_name = serializers.SerializerMethodField()

    class Meta:
        model = Backup
        fields = [
            "id",
            "name",
            "size_bytes",
            "kind",
            "status",
            "error",
            "created_at",
            "completed_at",
            "remote_status",
            "remote_destination",
            "remote_destination_name",
            "remote_key",
            "remote_error",
            "restore_status",
            "restore_error",
            "restored_at",
        ]
        read_only_fields = fields

    def get_remote_destination_name(self, obj: Backup) -> str:
        return obj.remote_destination.name if obj.remote_destination else ""
