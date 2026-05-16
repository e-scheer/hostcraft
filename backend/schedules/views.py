from __future__ import annotations

import threading
from datetime import datetime, timezone

from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import scheduler
from .models import Schedule
from .runners import HANDLERS
from .serializers import ScheduleSerializer


class ScheduleListCreateView(APIView):
    def get(self, _request: Request) -> Response:
        return Response({"entries": ScheduleSerializer(Schedule.objects.all(), many=True).data})

    def post(self, request: Request) -> Response:
        ser = ScheduleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=status.HTTP_201_CREATED)


class ScheduleDetailView(APIView):
    def get(self, _request: Request, pk: int) -> Response:
        sched = self._get(pk)
        if sched is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        return Response(ScheduleSerializer(sched).data)

    def patch(self, request: Request, pk: int) -> Response:
        sched = self._get(pk)
        if sched is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        ser = ScheduleSerializer(sched, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, _request: Request, pk: int) -> Response:
        sched = self._get(pk)
        if sched is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        sched.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _get(pk: int) -> Schedule | None:
        try:
            return Schedule.objects.get(pk=pk)
        except Schedule.DoesNotExist:
            return None


class ScheduleRunNowView(APIView):
    """POST /api/schedules/<id>/run/ — fire the schedule immediately, in a thread."""

    def post(self, _request: Request, pk: int) -> Response:
        try:
            sched = Schedule.objects.get(pk=pk)
        except Schedule.DoesNotExist:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)

        if sched.kind not in HANDLERS:
            return Response(
                {"detail": _("Unknown schedule kind.")}, status=status.HTTP_400_BAD_REQUEST
            )

        # Run in a daemon thread so the response is immediate.
        threading.Thread(
            target=scheduler._execute,  # noqa: SLF001 — single source of truth
            args=(sched, datetime.now(tz=timezone.utc)),
            daemon=True,
        ).start()
        return Response({"queued": True})
