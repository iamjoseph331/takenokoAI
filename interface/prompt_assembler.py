"""Prompt assembler — builds multi-part system prompts for each family module.

Concatenates four components wrapped in XML tags into a single system message:
  1. ``<identity>``  — short, static role description
  2. ``<self-model>`` — the full ``self.md`` (system awareness)
  3. ``<rulebook>``  — family-specific operational rules
  4. ``<character>`` — personality traits (Core + family section)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles

from interface.bus import FamilyPrefix
from interface.logging import ModuleLogger

if TYPE_CHECKING:
    from interface.character_model import CharacterModel
    from main import SelfModel


class PromptAssembler:
    """Assembles the 4-part system prompt for a single family module.

    Caches the assembled result. Call :meth:`reassemble` to force a
    re-read of all sources (e.g. after context compression or runtime
    updates to ``self.md`` / ``character.md``).
    """

    def __init__(
        self,
        family_prefix: FamilyPrefix,
        identity_path: str | Path,
        self_model: SelfModel,
        rulebook_path: str | Path,
        character_model: CharacterModel,
        logger: ModuleLogger,
    ) -> None:
        self._family_prefix = family_prefix
        self._identity_path = Path(identity_path)
        self._self_model = self_model
        self._rulebook_path = Path(rulebook_path)
        self._character_model = character_model
        self._logger = logger

        # Caches
        self._identity_cache: str | None = None
        self._rulebook_cache: str | None = None
        self._assembled_cache: str | None = None

    # ── Public API ──

    async def assemble(self) -> str:
        """Return the full system prompt, using cache if available."""
        if self._assembled_cache is not None:
            return self._assembled_cache

        identity = await self._load_identity()
        self_model_text = await self._load_self_model()
        rulebook = await self._load_rulebook()
        character = await self._load_character()

        parts: list[str] = []
        if identity:
            parts.append(self._wrap("identity", identity))
        if self_model_text:
            parts.append(self._wrap("self-model", self_model_text))
        if rulebook:
            parts.append(self._wrap("rulebook", rulebook))
        if character:
            parts.append(self._wrap("character", character))

        self._assembled_cache = "\n\n".join(parts)
        self._logger.action(
            f"Prompt assembled for {self._family_prefix.value}: "
            f"{len(self._assembled_cache)} chars"
        )
        return self._assembled_cache

    async def reassemble(self) -> str:
        """Invalidate all caches and re-assemble from disk."""
        self.invalidate_cache()
        return await self.assemble()

    def invalidate_cache(self) -> None:
        """Clear all cached prompt content."""
        self._identity_cache = None
        self._rulebook_cache = None
        self._assembled_cache = None

    # ── Loaders ──

    async def _load_identity(self) -> str:
        """Load the identity prompt file (cached after first read)."""
        if self._identity_cache is not None:
            return self._identity_cache

        if not self._identity_path.exists():
            self._logger.action(
                f"Identity prompt not found: {self._identity_path}"
            )
            self._identity_cache = ""
            return ""

        async with aiofiles.open(self._identity_path, "r", encoding="utf-8") as f:
            self._identity_cache = await f.read()
        return self._identity_cache

    async def _load_self_model(self) -> str:
        """Load the full self.md via SelfModel (always reads from SelfModel's cache)."""
        sections = await self._self_model.load_all()
        if not sections:
            return ""
        # Reconstruct the full document from sections
        lines: list[str] = []
        for header, body in sections.items():
            lines.append(f"## {header}\n{body}")
        return "".join(lines).strip()

    async def _load_rulebook(self) -> str:
        """Load the family's rulebook.md (cached after first read)."""
        if self._rulebook_cache is not None:
            return self._rulebook_cache

        if not self._rulebook_path.exists():
            self._logger.action(
                f"Rulebook not found: {self._rulebook_path}"
            )
            self._rulebook_cache = ""
            return ""

        async with aiofiles.open(self._rulebook_path, "r", encoding="utf-8") as f:
            self._rulebook_cache = await f.read()
        return self._rulebook_cache

    async def _load_character(self) -> str:
        """Load Core + family section from CharacterModel."""
        return await self._character_model.load_for_family(self._family_prefix)

    # ── Helpers ──

    @staticmethod
    def _wrap(tag: str, content: str) -> str:
        """Wrap content in XML-style delimiter tags."""
        return f"<{tag}>\n{content.strip()}\n</{tag}>"
