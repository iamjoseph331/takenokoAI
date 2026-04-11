"""Prompt assembler — builds multi-part system prompts for each family module.

Concatenates six components wrapped in XML tags into a single system message:
  1. ``<identity>``      — short, static role description
  2. ``<self-model>``    — the full ``self.md`` (system awareness)
  3. ``<rulebook>``      — family-specific operational rules
  4. ``<character>``     — personality traits (Core + family section)
  5. ``<lessons>``       — accumulated lessons the family writes to itself
  6. ``<output-format>`` — required JSON output format for LLM responses
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles

from interface.bus import FamilyPrefix
from interface.logging import ModuleLogger
from interface.message_codec import FORMAT_INSTRUCTIONS

if TYPE_CHECKING:
    from interface.character_model import CharacterModel
    from main import SelfModel

_FAMILY_FOLDER: dict[FamilyPrefix, str] = {
    FamilyPrefix.Re: "reaction",
    FamilyPrefix.Pr: "prediction",
    FamilyPrefix.Ev: "evaluation",
    FamilyPrefix.Me: "memorization",
    FamilyPrefix.Mo: "motion",
}


def default_lessons_path(family_prefix: FamilyPrefix) -> Path:
    """Return the conventional lessons file path for a family."""
    folder = _FAMILY_FOLDER[family_prefix]
    return Path(folder) / f"{family_prefix.value.lower()}_lessons.md"


class PromptAssembler:
    """Assembles the 6-part system prompt for a single family module.

    Caches the assembled result. Call :meth:`reassemble` to force a
    re-read of all sources (e.g. after context compression or runtime
    updates to ``self.md`` / ``character.md`` / ``lessons.md``).
    """

    def __init__(
        self,
        family_prefix: FamilyPrefix,
        identity_path: str | Path,
        self_model: SelfModel,
        rulebook_path: str | Path,
        character_model: CharacterModel,
        logger: ModuleLogger,
        lessons_path: str | Path | None = None,
    ) -> None:
        self._family_prefix = family_prefix
        self._identity_path = Path(identity_path)
        self._self_model = self_model
        self._rulebook_path = Path(rulebook_path)
        self._character_model = character_model
        self._logger = logger
        self._lessons_path = (
            Path(lessons_path) if lessons_path
            else default_lessons_path(family_prefix)
        )

        # Caches
        self._identity_cache: str | None = None
        self._rulebook_cache: str | None = None
        self._lessons_cache: str | None = None
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
        lessons = await self._load_lessons()

        parts: list[str] = []
        if identity:
            parts.append(self._wrap("identity", identity))
        if self_model_text:
            parts.append(self._wrap("self", self_model_text))
        if rulebook:
            parts.append(self._wrap("rulebook", rulebook))
        if character:
            parts.append(self._wrap("character", character))
        if lessons:
            parts.append(self._wrap("lessons", lessons))

        # Output format instructions (always included)
        parts.append(self._wrap("output-format", FORMAT_INSTRUCTIONS))

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
        self._lessons_cache = None
        self._assembled_cache = None

    # ── Lessons read/write ──

    async def read_lessons(self) -> str:
        """Read the family's lessons file from disk (bypasses cache)."""
        if not self._lessons_path.exists():
            return ""
        async with aiofiles.open(self._lessons_path, "r", encoding="utf-8") as f:
            return await f.read()

    async def write_lessons(self, content: str) -> None:
        """Overwrite the family's lessons file and invalidate prompt cache."""
        self._lessons_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._lessons_path, "w", encoding="utf-8") as f:
            await f.write(content)
        self._lessons_cache = None
        self._assembled_cache = None
        self._logger.action(
            f"Lessons updated for {self._family_prefix.value}: "
            f"{len(content)} chars"
        )

    async def append_lesson(self, lesson: str) -> None:
        """Append a single lesson entry to the family's lessons file."""
        existing = await self.read_lessons()
        separator = "\n" if existing and not existing.endswith("\n") else ""
        await self.write_lessons(f"{existing}{separator}{lesson}\n")

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
        """Load all sections from self.md for full cross-family awareness."""
        sections = await self._self_model.load_all()
        if not sections:
            return ""
        lines: list[str] = []
        for header, body in sections.items():
            if not body:
                continue
            if header == "_preamble":
                lines.append(body.strip())
            else:
                lines.append(f"## {header}\n{body.strip()}")
        return "\n\n".join(lines) if lines else ""

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

    async def _load_lessons(self) -> str:
        """Load the family's lessons file (cached after first read)."""
        if self._lessons_cache is not None:
            return self._lessons_cache

        if not self._lessons_path.exists():
            self._logger.action(
                f"Lessons file not found: {self._lessons_path}"
            )
            self._lessons_cache = ""
            return ""

        async with aiofiles.open(self._lessons_path, "r", encoding="utf-8") as f:
            self._lessons_cache = await f.read()
        return self._lessons_cache

    async def _load_character(self) -> str:
        """Load Core + family section from CharacterModel."""
        return await self._character_model.load_for_family(self._family_prefix)

    # ── Helpers ──

    @staticmethod
    def _wrap(tag: str, content: str) -> str:
        """Wrap content in XML-style delimiter tags."""
        return f"<{tag}>\n{content.strip()}\n</{tag}>"
