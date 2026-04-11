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

import html as html_lib

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from interface.bus import BusMessage, MessageBus
from interface.logging import ModuleLogger

_HTML_PATH = Path(__file__).parent / "viz_ui.html"


def _render_prompt_page(
    msg_id: str,
    data: dict[str, Any] | None,
    *,
    note: str | None = None,
) -> str:
    """Render the prompt-inspection HTML page for /prompt/{msg_id}."""
    esc = html_lib.escape
    header = (
        "<style>"
        "body{background:#0d1117;color:#e6edf3;"
        "font-family:'JetBrains Mono','Fira Code',monospace;"
        "margin:0;padding:24px;line-height:1.5;}"
        "h1{font-size:16px;color:#a5d6ff;margin:0 0 4px 0;}"
        ".sub{font-size:12px;color:#8b949e;margin-bottom:20px;}"
        ".meta{background:#161b22;border:1px solid #30363d;"
        "border-radius:6px;padding:10px 14px;margin-bottom:20px;"
        "font-size:12px;color:#8b949e;}"
        ".meta b{color:#e6edf3;}"
        ".msg{background:#161b22;border:1px solid #30363d;"
        "border-left:3px solid #58a6ff;border-radius:6px;"
        "padding:12px 16px;margin-bottom:14px;}"
        ".msg.system{border-left-color:#d2a8ff;}"
        ".msg.user{border-left-color:#3fb950;}"
        ".msg.assistant{border-left-color:#e3b341;}"
        ".msg .role{font-size:11px;text-transform:uppercase;"
        "letter-spacing:1px;color:#8b949e;margin-bottom:8px;}"
        ".msg pre{margin:0;white-space:pre-wrap;word-break:break-word;"
        "font-family:inherit;font-size:12.5px;color:#e6edf3;}"
        ".note{background:#1c1d00;border:1px solid #3d3d00;"
        "color:#d29922;padding:10px 14px;border-radius:6px;"
        "margin-bottom:20px;font-size:12px;}"
        "</style>"
    )

    body_parts = [
        f"<h1>Prompt for {esc(msg_id)}</h1>",
        "<div class='sub'>Full LLM request as sent by the family module</div>",
    ]
    if note:
        body_parts.append(f"<div class='note'>{esc(note)}</div>")

    if data is not None:
        meta = data.get("meta") or {}
        sender = data.get("sender", "?")
        ts = data.get("ts", 0)
        meta_line = (
            f"<div class='meta'>"
            f"<b>sender:</b> {esc(str(sender))} &nbsp;·&nbsp; "
            f"<b>model:</b> {esc(str(meta.get('model', '?')))} &nbsp;·&nbsp; "
            f"<b>temperature:</b> {esc(str(meta.get('temperature', '?')))} &nbsp;·&nbsp; "
            f"<b>max_tokens:</b> {esc(str(meta.get('max_tokens', '?')))} &nbsp;·&nbsp; "
            f"<b>ts:</b> {esc(str(round(float(ts), 3)))}"
            f"</div>"
        )
        body_parts.append(meta_line)

        for m in data.get("messages", []):
            role = str(m.get("role", "?"))
            content = str(m.get("content", ""))
            body_parts.append(
                f"<div class='msg {esc(role)}'>"
                f"<div class='role'>{esc(role)}</div>"
                f"<pre>{esc(content)}</pre>"
                f"</div>"
            )

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>Prompt · {esc(msg_id)}</title>"
        f"{header}</head><body>"
        + "".join(body_parts)
        + "</body></html>"
    )


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

        @app.get("/prompt/{msg_id}")
        async def get_prompt(msg_id: str) -> HTMLResponse:
            """Render the LLM prompt attributed to a bus message.

            Returns a standalone HTML page suitable for opening in a new
            tab when a user double-clicks a message in the feed.
            """
            if broadcaster._bus is None:
                raise HTTPException(503, "bus not attached")
            data = broadcaster._bus.get_prompt(msg_id)
            if data is None:
                return HTMLResponse(
                    _render_prompt_page(
                        msg_id,
                        None,
                        note=(
                            "No prompt recorded for this message. "
                            "It was either produced without an LLM call "
                            "(e.g. Mo.speak), attributed to another message, "
                            "or evicted from the bounded log."
                        ),
                    ),
                    status_code=404,
                )
            return HTMLResponse(_render_prompt_page(msg_id, data))

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
