from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter
from django.utils.translation import gettext as _
from rest_framework import serializers

from .models import Schedule


class ScheduleSerializer(serializers.ModelSerializer):
    next_run_at = serializers.SerializerMethodField()

    class Meta:
        model = Schedule
        fields = [
            "id",
            "name",
            "kind",
            "cron",
            "payload",
            "enabled",
            "last_run_at",
            "last_status",
            "last_error",
            "next_run_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "last_run_at",
            "last_status",
            "last_error",
            "next_run_at",
            "created_at",
            "updated_at",
        ]

    def get_next_run_at(self, obj: Schedule) -> str | None:
        try:
            nxt = croniter(obj.cron, datetime.now(tz=timezone.utc)).get_next(datetime)
        except (ValueError, KeyError):
            return None
        return nxt.isoformat()

    def validate_cron(self, value: str) -> str:
        if not croniter.is_valid(value):
            raise serializers.ValidationError(_("Invalid cron expression."))
        return value

    def validate_kind(self, value: str) -> str:
        if value not in dict(Schedule.Kind.choices):
            raise serializers.ValidationError(_("Unknown schedule kind."))
        return value

    def validate(self, attrs: dict) -> dict:
        kind = attrs.get("kind") or getattr(self.instance, "kind", None)
        payload = attrs.get("payload") or {}
        if kind == Schedule.Kind.RCON and not (payload.get("command") or "").strip():
            raise serializers.ValidationError({"payload": _("RCON schedules require a command.")})
        return attrs
