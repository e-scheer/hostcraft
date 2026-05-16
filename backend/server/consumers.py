"""WebSocket consumers for the live console.

Wire format (JSON):
    Server → Client:
        {"type": "info",  "text": "..."}            # connection events
        {"type": "log",   "text": "...", "level": "info|warn|error"}  # streamed Docker logs
        {"type": "reply", "id": "...", "text": "..."}  # response to a cmd
        {"type": "error", "id": "...", "text": "..."}  # cmd failed (id may be absent)

    Client → Server:
        {"type": "cmd",   "id": "...", "text": "say hello"}
"""

from __future__ import annotations

import asyncio
import logging
import threading

import docker
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from . import rcon

logger = logging.getLogger(__name__)


class ConsoleConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close(code=4401)
            return
        await self.accept()
        await self.send_json({"type": "info", "text": "Connected · streaming logs"})

        self._stop = threading.Event()
        self._queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        loop = asyncio.get_running_loop()
        threading.Thread(target=self._log_producer, args=(loop,), daemon=True).start()
        self._pump_task = asyncio.create_task(self._log_pump())

    async def disconnect(self, _code):
        if hasattr(self, "_stop"):
            self._stop.set()
        if hasattr(self, "_pump_task"):
            self._pump_task.cancel()

    async def receive_json(self, content, **_kwargs):
        if content.get("type") != "cmd":
            return
        cmd_id = str(content.get("id") or "")
        cmd = (content.get("text") or "").strip()
        if not cmd:
            return
        try:
            reply = await database_sync_to_async(rcon.send)(cmd)
        except rcon.RconUnavailable as exc:
            await self.send_json({"type": "error", "id": cmd_id, "text": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 — surface anything to UI
            logger.exception("RCON cmd failed")
            await self.send_json({"type": "error", "id": cmd_id, "text": f"{type(exc).__name__}: {exc}"})
            return
        await self.send_json({"type": "reply", "id": cmd_id, "text": reply or "(no output)"})

    # ------------------------------------------------------------------
    # Log streaming: Docker SDK is sync-blocking, so we run it in a thread
    # and push lines into an asyncio.Queue read by an async pump.
    # ------------------------------------------------------------------

    def _log_producer(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            client = docker.DockerClient(base_url=settings.DOCKER_HOST, timeout=10)
            container = client.containers.get(settings.MC_CONTAINER_NAME)
            stream = container.logs(stream=True, follow=True, tail=200)
            for chunk in stream:
                if self._stop.is_set():
                    break
                if not chunk:
                    continue
                text = chunk.decode("utf-8", errors="replace").rstrip("\r\n")
                if text:
                    asyncio.run_coroutine_threadsafe(self._queue.put(("log", text)), loop)
        except Exception as exc:  # noqa: BLE001
            logger.exception("log producer crashed")
            asyncio.run_coroutine_threadsafe(
                self._queue.put(("error", f"Log stream stopped: {exc}")), loop
            )

    async def _log_pump(self) -> None:
        try:
            while True:
                kind, text = await self._queue.get()
                await self.send_json({"type": kind, "text": text})
        except asyncio.CancelledError:
            pass
