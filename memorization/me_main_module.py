"""Memorization family main module — stores and retrieves information."""

from __future__ import annotations

from typing import Any, Optional

from interface.bus import FamilyPrefix, MessageBus
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import MainModule
from interface.permissions import PermissionManager
from interface.prompt_assembler import PromptAssembler


class MemorizationModule(MainModule):
    """Manages short-term, long-term memory and logs.

    Receives storage/retrieval requests from other families (via D path from Pr,
    or P path from Ev).
    """

    def __init__(
        self,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
        prompt_assembler: PromptAssembler | None = None,
    ) -> None:
        super().__init__(
            FamilyPrefix.Me, bus, logger, llm_config, permissions,
            prompt_assembler=prompt_assembler,
        )

    async def store(
        self,
        content: Any,
        *,
        tags: list[str] | None = None,
        memory_type: str = "short_term",
    ) -> str:
        """Store content in memory and return a memory_id.

        Args:
            content: The data to store.
            tags: Optional tags for categorization.
            memory_type: One of "short_term", "long_term", "log".

        Returns:
            A unique memory_id string.
        """
        raise NotImplementedError(
            "store: persist content with tags and memory_type, return memory_id"
        )

    async def search(
        self,
        query: str,
        *,
        memory_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search stored memories by query.

        Args:
            query: Search query string.
            memory_type: Filter by type, or None for all.
            limit: Max results to return.

        Returns:
            List of matching memory records.
        """
        raise NotImplementedError(
            "search: query memories filtered by type, return up to limit results"
        )

    async def recall(self, memory_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a specific memory by its ID.

        Returns the memory record or None if not found.
        """
        raise NotImplementedError("recall: retrieve memory by memory_id")

    async def _message_loop(self) -> None:
        """Listen for store/search/recall requests from other families."""
        raise NotImplementedError("MemorizationModule._message_loop")

    async def get_resources(self) -> dict[str, Any]:
        raise NotImplementedError("MemorizationModule.get_resources")

    async def get_limits(self) -> dict[str, Any]:
        raise NotImplementedError("MemorizationModule.get_limits")

    async def pause_and_answer(
        self, question: str, requester: FamilyPrefix
    ) -> str:
        raise NotImplementedError("MemorizationModule.pause_and_answer")
