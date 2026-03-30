"""Visualization server — broadcasts agent state over WebSocket.

Runs in the same asyncio event loop as the agent.
Serves:
  GET /      → viz_ui.html
  WS  /ws    → live JSON event stream

Two event types pushed to connected browsers:
  {"type": "msg",      "src": .., "dst": .., "path": .., "summary": .., "is_ack": .., "ts": ..}
  {"type": "snapshot", "states": {..}, "queue_depths": {..}, "broadcasts": [..], "uptime": ..}
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from interface.bus import BusMessage, MessageBus
from interface.logging import ModuleLogger

_HTML_PATH = Path(__file__).parent / "viz_ui.html"


class VizBroadcaster:
    """WebSocket broadcaster for live TakenokoAI visualization."""

    def __init__(
        self,
        port: int = 7899,
        families: dict[str, Any] | None = None,
    ) -> None:
        self._port = port
        self._families = families or {}
        self._logger = ModuleLogger("VIZ", "broadcaster")
        self._bus: MessageBus | None = None
        self._clients: Set[WebSocket] = set()
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2000)
        self._start_time: float = time.monotonic()
        self._app = self._build_app()

    def attach(self, bus: MessageBus) -> None:
        """Wire into the bus's viz hook."""
        self._bus = bus
        bus.viz_hook = self._on_bus_message
        self._start_time = time.monotonic()
        self._logger.action(f"VizBroadcaster attached to bus (port={self._port})")

    def _on_bus_message(self, message: BusMessage) -> None:
        """Called synchronously by MessageBus.send() for every message."""
        event = json.dumps({
            "type": "msg",
            "src": message.sender.value,
            "dst": message.receiver.value,
            "path": message.message_id[-1] if message.message_id else "?",
            "summary": message.summary or str(message.body)[:80] if not message.is_ack else "ack",
            "is_ack": message.is_ack,
            "msg_id": message.message_id,
            "trace_id": message.trace_id,
            "ts": round(time.monotonic() - self._start_time, 3),
        })
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def _build_snapshot(self) -> dict:
        states = {
            prefix: str(module.state)  # type: ignore[attr-defined]
            for prefix, module in self._families.items()
        }
        queue_depths = {}
        if self._bus:
            for prefix in ("Re", "Pr", "Ev", "Me", "Mo"):
                q = self._bus._queues.get(f"{prefix}.main")
                queue_depths[prefix] = q.qsize() if q else 0

        broadcasts: list[dict] = []
        if self._bus:
            for b in self._bus.get_recent_broadcasts(10):
                broadcasts.append({
                    "sender": b.sender,
                    "summary": b.summary,
                    "ts": round(b.timecode - self._start_time, 3),
                })

        return {
            "type": "snapshot",
            "states": states,
            "queue_depths": queue_depths,
            "broadcasts": broadcasts,
            "uptime": round(time.monotonic() - self._start_time, 1),
        }

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="TakenokoAI Visualizer", docs_url=None, redoc_url=None)
        broadcaster = self

        @app.get("/")
        async def serve_ui() -> HTMLResponse:
            if _HTML_PATH.exists():
                return HTMLResponse(_HTML_PATH.read_text(encoding="utf-8"))
            return HTMLResponse("<h1>viz_ui.html not found</h1>", status_code=404)

        @app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket) -> None:
            await ws.accept()
            broadcaster._clients.add(ws)
            broadcaster._logger.action(
                f"WS client connected ({len(broadcaster._clients)} total)"
            )
            try:
                # Send initial snapshot
                await ws.send_text(json.dumps(broadcaster._build_snapshot()))
                while True:
                    try:
                        await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                    except asyncio.TimeoutError:
                        await ws.send_text('{"type":"ping"}')
            except (WebSocketDisconnect, Exception):
                pass
            finally:
                broadcaster._clients.discard(ws)
                broadcaster._logger.action(
                    f"WS client disconnected ({len(broadcaster._clients)} total)"
                )

        return app

    async def _broadcast_loop(self) -> None:
        last_snapshot = time.monotonic()
        SNAPSHOT_INTERVAL = 0.5  # 2 Hz

        while True:
            # Drain pending message events
            while True:
                try:
                    event = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                await self._broadcast(event)

            # Periodic snapshot
            now = time.monotonic()
            if now - last_snapshot >= SNAPSHOT_INTERVAL and self._clients:
                await self._broadcast(json.dumps(self._build_snapshot()))
                last_snapshot = now

            await asyncio.sleep(0.05)  # 20 Hz drain

    async def _broadcast(self, text: str) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def run(self) -> None:
        config = uvicorn.Config(
            app=self._app,
            host="0.0.0.0",
            port=self._port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        server.config.setup_event_loop = lambda: None
        self._logger.action(f"VizBroadcaster running on port {self._port}")
        await asyncio.gather(server.serve(), self._broadcast_loop())
