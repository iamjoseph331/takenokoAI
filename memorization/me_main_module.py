"""Memorization family main module — stores and retrieves information.

Stage 1: logs-only implementation. Short-term and long-term memory are
deferred to Stage 2.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from interface.bus import BusMessage, FamilyPrefix, MessageBus
from interface.llm import CompletionFn, LLMConfig
from interface.logging import ModuleLogger
from interface.modules import MainModule
from interface.permissions import PermissionManager
from interface.prompt_assembler import PromptAssembler


class MemorizationModule(MainModule):
    """Manages short-term, long-term memory and logs.

    Stage 1: in-memory dict store with tag-based search. Logs only.
    """

    def __init__(
        self,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
        prompt_assembler: PromptAssembler | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            FamilyPrefix.Me, bus, logger, llm_config, permissions,
            prompt_assembler=prompt_assembler,
            completion_fn=completion_fn,
        )
        self._store: dict[str, dict[str, Any]] = {}

    async def store(
        self,
        content: Any,
        *,
        tags: list[str] | None = None,
        memory_type: str = "log",
        source: str = "",
    ) -> str:
        """Store content in memory and return a memory_id."""
        memory_id = f"mem_{uuid.uuid4().hex[:8]}"
        record = {
            "memory_id": memory_id,
            "content": content,
            "tags": tags or [],
            "memory_type": memory_type,
            "source": source,
            "timestamp": time.time(),
        }
        self._store[memory_id] = record
        self._logger.action(
            f"Stored memory {memory_id}",
            data={"type": memory_type, "tags": tags, "source": source},
        )
        return memory_id

    async def search(
        self,
        query: str,
        *,
        memory_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search stored memories by query string (simple substring match).

        Stage 1: no embedding search, just substring matching on content.
        """
        results: list[dict[str, Any]] = []
        query_lower = query.lower()
        for record in self._store.values():
            if memory_type and record["memory_type"] != memory_type:
                continue
            content_str = str(record["content"]).lower()
            tags_str = " ".join(record.get("tags", [])).lower()
            if query_lower in content_str or query_lower in tags_str:
                results.append(record)
            if len(results) >= limit:
                break
        return results

    async def recall(self, memory_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a specific memory by its ID."""
        record = self._store.get(memory_id)
        if record is None:
            self._logger.action(f"recall: memory {memory_id} not found")
        return record

    async def _handle_message(self, message: BusMessage) -> None:
        """Handle store/search/recall requests from other families."""
        body = message.body or {}
        if not isinstance(body, dict):
            self._logger.action(
                f"Me received non-dict body from {message.sender}",
                data={"body_preview": str(body)[:200]},
            )
            return

        action = body.get("action", "store")

        if action == "store":
            content = body.get("content", body.get("plan", str(body)))
            memory_id = await self.store(
                content=content,
                tags=body.get("tags", []),
                memory_type=body.get("memory_type", "log"),
                source=message.sender.value,
            )
            self._logger.action(
                f"Stored from {message.sender}: {memory_id}"
            )

        elif action == "search":
            results = await self.search(
                query=body.get("query", ""),
                memory_type=body.get("memory_type"),
                limit=body.get("limit", 10),
            )
            self._logger.action(
                f"Search from {message.sender}: {len(results)} results"
            )

        elif action == "recall":
            record = await self.recall(body.get("memory_id", ""))
            self._logger.action(
                f"Recall from {message.sender}: {'found' if record else 'not found'}"
            )

        else:
            # Default: store the message body as a log
            await self.store(
                content=body,
                tags=["auto_log"],
                memory_type="log",
                source=message.sender.value,
            )
