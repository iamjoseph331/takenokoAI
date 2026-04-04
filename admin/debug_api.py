"""
DebugServer — REST API for pausing, stepping, injecting messages, and operator Q&A.

Endpoints:
  GET  /state                → {paused, queue_depths, family_states, stats}
  GET  /families             → list of families with state and queue info
  GET  /family/{prefix}/tasks → peek at queued messages for a family
  POST /pause                → pause all module loops (bus stops delivering)
  POST /resume               → resume all module loops
  POST /step                 → resume for `duration` seconds then re-pause
  POST /inject               → send a raw BusMessage to any family
  POST /talk/{prefix}        → send text to a family's LLM and get the response
  POST /ask                  → ask Pr (or any family) a question using live context
  GET  /models               → list available models from Ollama
  GET  /families/models      → current model config per family
  POST /family/{prefix}/model → change model (and optionally temperature) for a family

Usage:
  dbg = DebugServer(port=7901)
  dbg.attach(bus, agent)
  asyncio.create_task(dbg.run())

Example curl:
  curl localhost:7901/state
  curl -X POST localhost:7901/pause
  curl -X POST localhost:7901/step?duration=1.0
  curl -X POST localhost:7901/resume
  curl -X POST localhost:7901/inject \\
       -H 'Content-Type: application/json' \\
       -d '{"target":"Mo","text":"hello world","path":"D","context":"debug"}'
  curl -X POST localhost:7901/talk/Pr \\
       -H 'Content-Type: application/json' \\
       -d '{"text":"What is 2+2?"}'
  curl -X POST localhost:7901/ask \\
       -H 'Content-Type: application/json' \\
       -d '{"question":"What are you currently doing?"}'
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import TYPE_CHECKING, Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from interface.bus import MessageBus
    from main import TakenokoAgent

# Known family prefixes
KNOWN_FAMILIES = ["Re", "Pr", "Ev", "Me", "Mo"]

# Prompt addendum for operator Q&A mode
_ASK_ADDENDUM = """

---
You are now answering a question from the human operator who is monitoring you.
- Answer in plain prose; be concise and direct.
- Base your answer on the context provided.
- Do NOT issue any agent commands or bus messages.
"""


# ── Request / Response models ────────────────────────────────────────────────


class InjectRequest(BaseModel):
    target: str = Field(..., description="Target family prefix (Re, Pr, Ev, Me, Mo)")
    text: str = Field(..., description="Message body text")
    path: str = Field(default="D", description="Cognition path letter (P, R, E, U, D)")
    context: str = Field(default="debug_inject", description="Message context tag")


class TalkRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to send to the family's LLM")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question for the agent")
    target: str = Field(default="Pr", description="Family to ask (default: Pr)")


class ModelChangeRequest(BaseModel):
    model: str = Field(..., description="Model name (e.g. 'ollama/gemma4')")
    temperature: float | None = Field(None, description="Optional temperature override")


# ── DebugServer ──────────────────────────────────────────────────────────────


class DebugServer:
    """REST debug API that runs alongside the agent in the same event loop."""

    def __init__(self, port: int = 7901) -> None:
        self._port = port
        self._bus: MessageBus | None = None
        self._agent: TakenokoAgent | None = None
        self._start_time = time.monotonic()
        self._app = self._build_app()

    def attach(self, bus: MessageBus, agent: TakenokoAgent) -> None:
        """Attach to the live bus and agent. Call before run()."""
        self._bus = bus
        self._agent = agent
        self._start_time = time.monotonic()

    async def run(self) -> None:
        """Start the uvicorn server."""
        config = uvicorn.Config(
            app=self._app,
            host="0.0.0.0",
            port=self._port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        print(
            f"[debug] REST API → http://localhost:{self._port}  "
            f"(pause/resume/step/inject/talk/ask/state)",
            file=sys.stderr,
        )
        await server.serve()

    # ── FastAPI app ──────────────────────────────────────────────────────────

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="TakenokoAI Debug API", version="1.0")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        srv = self

        # ── helpers ──────────────────────────────────────────────────────────

        def _require_bus() -> "MessageBus":
            if srv._bus is None:
                raise HTTPException(status_code=503, detail="Bus not attached")
            return srv._bus

        def _require_agent() -> "TakenokoAgent":
            if srv._agent is None:
                raise HTTPException(status_code=503, detail="Agent not attached")
            return srv._agent

        def _get_family_state(prefix: str) -> str:
            agent = srv._agent
            if agent is None:
                return "unknown"
            from interface.bus import FamilyPrefix
            try:
                mod = agent.get_family(FamilyPrefix(prefix))
                return str(mod.state)
            except (KeyError, ValueError):
                return "unknown"

        def _peek_queue(prefix: str) -> list[dict[str, Any]]:
            """Peek into a family's bus queue without consuming messages."""
            bus = srv._bus
            if bus is None:
                return []
            tasks: list[dict[str, Any]] = []
            for qname, q in bus._queues.items():
                if qname == prefix or qname.startswith(f"{prefix}."):
                    internal = getattr(q, "_queue", None)
                    if internal is not None:
                        for item in list(internal):
                            sender_val = (
                                item.sender.value
                                if hasattr(item.sender, "value")
                                else str(item.sender)
                            )
                            tasks.append({
                                "message_id": item.message_id,
                                "sender": sender_val,
                                "context": (item.context or "")[:120],
                                "body": str(item.body)[:200] if item.body else "",
                                "trace_id": item.trace_id or "",
                                "is_ack": item.is_ack,
                            })
            return tasks

        # ── GET /state ───────────────────────────────────────────────────────

        @app.get("/state")
        async def get_state() -> dict:
            bus = _require_bus()
            paused = not bus.pause_event.is_set()

            queue_depths: dict[str, int] = {}
            for prefix in KNOWN_FAMILIES:
                depth = 0
                for qname, q in bus._queues.items():
                    if qname == prefix or qname.startswith(f"{prefix}."):
                        depth += q.qsize()
                queue_depths[prefix] = depth

            family_states = {p: _get_family_state(p) for p in KNOWN_FAMILIES}

            return {
                "paused": paused,
                "queue_depths": queue_depths,
                "family_states": family_states,
                "stats": {
                    "uptime": round(time.monotonic() - srv._start_time, 1),
                },
            }

        # ── GET /families ────────────────────────────────────────────────────

        @app.get("/families")
        async def get_families() -> dict:
            bus = _require_bus()
            families = []
            for prefix in KNOWN_FAMILIES:
                depth = 0
                maxsize = 0
                registered = False
                for qname, q in bus._queues.items():
                    if qname == prefix or qname.startswith(f"{prefix}."):
                        depth += q.qsize()
                        maxsize = q.maxsize
                        registered = True
                families.append({
                    "prefix": prefix,
                    "registered": registered,
                    "state": _get_family_state(prefix),
                    "queue_depth": depth,
                    "queue_maxsize": maxsize,
                })
            return {"families": families}

        # ── GET /family/{prefix}/tasks ───────────────────────────────────────

        @app.get("/family/{prefix}/tasks")
        async def get_family_tasks(prefix: str) -> dict:
            if prefix not in KNOWN_FAMILIES:
                raise HTTPException(404, f"Unknown family: {prefix}")
            tasks = _peek_queue(prefix)
            return {"family": prefix, "tasks": tasks, "count": len(tasks)}

        # ── POST /pause ──────────────────────────────────────────────────────

        @app.post("/pause")
        async def pause() -> dict:
            bus = _require_bus()
            bus.pause_event.clear()
            return {"status": "paused"}

        # ── POST /resume ─────────────────────────────────────────────────────

        @app.post("/resume")
        async def resume() -> dict:
            bus = _require_bus()
            bus.pause_event.set()
            return {"status": "running"}

        # ── POST /step ───────────────────────────────────────────────────────

        @app.post("/step")
        async def step(duration: float = 0.5) -> dict:
            """Resume for `duration` seconds (0.05–10.0), then re-pause."""
            bus = _require_bus()
            duration = max(0.05, min(duration, 10.0))
            bus.pause_event.set()
            await asyncio.sleep(duration)
            bus.pause_event.clear()
            return {"status": "stepped", "duration": duration}

        # ── POST /inject ─────────────────────────────────────────────────────

        @app.post("/inject")
        async def inject(body: InjectRequest) -> dict:
            """Inject a message directly into a family's bus queue."""
            bus = _require_bus()
            agent = _require_agent()

            if body.target not in KNOWN_FAMILIES:
                raise HTTPException(400, f"Unknown target family: {body.target}")

            from interface.bus import (
                BusMessage,
                CognitionPath,
                FamilyPrefix,
                MessageBus,
            )

            # Use Pr as the sender for injected messages (it has universal dispatch)
            sender = FamilyPrefix.Pr
            try:
                target = FamilyPrefix(body.target)
            except ValueError:
                raise HTTPException(400, f"Invalid family prefix: {body.target}")

            try:
                path = CognitionPath(body.path)
            except ValueError:
                raise HTTPException(400, f"Invalid path: {body.path}")

            # Generate a message ID through the Pr module
            pr_module = agent.get_family(FamilyPrefix.Pr)
            msg_id = pr_module.next_message_id(path)

            message = BusMessage(
                message_id=msg_id,
                timecode=MessageBus.now(),
                context=body.context,
                body={"text": body.text},
                sender=sender,
                receiver=target,
                trace_id=f"dbg-{msg_id}",
            )

            result = await bus.send(message)
            if result is not None:
                return {
                    "status": "queue_full",
                    "message_id": msg_id,
                    "queue_size": result.queue_size,
                }
            return {"status": "queued", "message_id": msg_id, "target": body.target}

        # ── POST /talk/{prefix} ──────────────────────────────────────────────

        @app.post("/talk/{prefix}")
        async def talk(prefix: str, body: TalkRequest) -> dict:
            """Send text directly to a family's LLM and return the response.

            Bypasses the bus entirely — calls the module's LLM client directly.
            Useful for testing prompts and LLM configuration.
            """
            agent = _require_agent()
            if prefix not in KNOWN_FAMILIES:
                raise HTTPException(404, f"Unknown family: {prefix}")

            from interface.bus import FamilyPrefix

            try:
                module = agent.get_family(FamilyPrefix(prefix))
            except (KeyError, ValueError) as e:
                raise HTTPException(404, str(e))

            messages = [{"role": "user", "content": body.text}]
            try:
                response = await module.think(messages)
            except Exception as e:
                raise HTTPException(
                    502, f"LLM call failed: {type(e).__name__}: {e}"
                )

            return {
                "family": prefix,
                "response": response,
                "model": module._llm._config.model_name,
            }

        # ── POST /ask ────────────────────────────────────────────────────────

        @app.post("/ask")
        async def ask(body: AskRequest) -> dict:
            """Ask a family a question with live agent context injected.

            Builds a snapshot of the agent's current state (queue depths,
            family states, recent bus activity) and includes it alongside
            the operator's question. The family's LLM answers in prose.
            """
            agent = _require_agent()
            bus = _require_bus()

            if body.target not in KNOWN_FAMILIES:
                raise HTTPException(400, f"Unknown target: {body.target}")

            from interface.bus import FamilyPrefix

            try:
                module = agent.get_family(FamilyPrefix(body.target))
            except (KeyError, ValueError) as e:
                raise HTTPException(404, str(e))

            # Build context snapshot
            queue_depths = {}
            for p in KNOWN_FAMILIES:
                depth = 0
                for qname, q in bus._queues.items():
                    if qname == p or qname.startswith(f"{p}."):
                        depth += q.qsize()
                queue_depths[p] = depth

            family_states = {p: _get_family_state(p) for p in KNOWN_FAMILIES}
            paused = not bus.pause_event.is_set()

            context_lines = [
                f"AGENT STATE: {'PAUSED' if paused else 'RUNNING'}",
                f"QUEUE DEPTHS: {queue_depths}",
                f"FAMILY STATES: {family_states}",
                "",
                f"OPERATOR QUESTION: {body.question}",
            ]
            user_msg = "\n".join(context_lines)

            # Prepend operator addendum to the user message
            messages = [{"role": "user", "content": _ASK_ADDENDUM + "\n" + user_msg}]
            try:
                answer = await module.think(messages)
            except Exception as e:
                raise HTTPException(
                    502, f"LLM call failed: {type(e).__name__}: {e}"
                )

            return {
                "answer": answer,
                "context": {
                    "target": body.target,
                    "paused": paused,
                    "queue_depths": queue_depths,
                    "family_states": family_states,
                },
            }

        # ── GET /models ─────────────────────────────────────────────────────

        @app.get("/models")
        async def list_models() -> dict:
            """List available models from Ollama's local API."""
            ollama_url = "http://localhost:11434/api/tags"
            models: list[dict[str, Any]] = []
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(ollama_url)
                    resp.raise_for_status()
                    data = resp.json()
                    for m in data.get("models", []):
                        name = m.get("name", "")
                        models.append({
                            "name": f"ollama/{name}",
                            "raw_name": name,
                            "size": m.get("size"),
                        })
            except Exception as e:
                return {
                    "models": models,
                    "error": f"Could not reach Ollama: {type(e).__name__}: {e}",
                }
            return {"models": models}

        # ── GET /families/models ─────────────────────────────────────────────

        @app.get("/families/models")
        async def get_family_models() -> dict:
            """Return current model configuration for all families."""
            agent = _require_agent()
            from interface.bus import FamilyPrefix

            result: dict[str, dict[str, Any]] = {}
            for prefix_str in KNOWN_FAMILIES:
                try:
                    module = agent.get_family(FamilyPrefix(prefix_str))
                    cfg = module._llm._config
                    result[prefix_str] = {
                        "model": cfg.model_name,
                        "temperature": cfg.temperature,
                        "max_tokens": cfg.max_tokens,
                    }
                except (KeyError, ValueError):
                    result[prefix_str] = {"model": "unknown", "temperature": 0, "max_tokens": 0}
            return {"families": result}

        # ── POST /family/{prefix}/model ──────────────────────────────────────

        @app.post("/family/{prefix}/model")
        async def change_family_model(prefix: str, body: ModelChangeRequest) -> dict:
            """Change the LLM model (and optionally temperature) for a family."""
            agent = _require_agent()
            if prefix not in KNOWN_FAMILIES:
                raise HTTPException(404, f"Unknown family: {prefix}")

            from interface.bus import FamilyPrefix

            try:
                module = agent.get_family(FamilyPrefix(prefix))
            except (KeyError, ValueError) as e:
                raise HTTPException(404, str(e))

            # Update model name
            module._llm.update_config(model_name=body.model)

            # Update temperature if provided
            if body.temperature is not None:
                module._llm.update_config(temperature=body.temperature)

            cfg = module._llm._config
            return {
                "status": "ok",
                "family": prefix,
                "model": cfg.model_name,
                "temperature": cfg.temperature,
            }

        return app
