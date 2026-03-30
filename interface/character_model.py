"""Character model manager — read-write personality definitions.

Mirrors the SelfModel pattern: a single ``character.md`` at the project root
with ``## Section`` headers.  Each family can read and write its own section.
``<Pr>`` has default authority to write any section.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiofiles

from interface.bus import FamilyPrefix
from interface.logging import ModuleLogger
from interface.markdown_utils import parse_markdown_sections
from interface.permissions import PermissionAction, PermissionManager


class CharacterModel:
    """Manages ``character.md`` — the agent's personality definitions.

    Sections:
        - ``Core`` — shared personality traits for all families
        - ``Re``, ``Pr``, ``Ev``, ``Me``, ``Mo`` — per-family overrides
    """

    def __init__(
        self,
        path: str | Path,
        permissions: PermissionManager,
        logger: ModuleLogger,
    ) -> None:
        self._path = Path(path)
        self._permissions = permissions
        self._logger = logger
        self._sections: dict[str, str] = {}
        self._raw: str = ""
        self._lock = asyncio.Lock()
        self._loaded: bool = False

    async def load_all(self) -> str:
        """Read the entire character.md and cache it. Returns raw content."""
        async with self._lock:
            if not self._path.exists():
                self._logger.action(
                    f"character.md not found at {self._path}, starting empty"
                )
                self._sections = {}
                self._raw = ""
                self._loaded = True
                return ""

            async with aiofiles.open(self._path, "r", encoding="utf-8") as f:
                self._raw = await f.read()

            self._sections = parse_markdown_sections(self._raw)
            self._loaded = True
            self._logger.action(
                f"Loaded character.md: {len(self._sections)} sections"
            )
            return self._raw

    async def _ensure_loaded(self) -> None:
        """Lazy-load if not yet loaded."""
        if not self._loaded:
            await self.load_all()

    async def load_section(self, section: str) -> str:
        """Read a single section by header name."""
        await self._ensure_loaded()
        async with self._lock:
            return self._sections.get(section, "")

    async def load_for_family(self, family_prefix: FamilyPrefix) -> str:
        """Return ``## Core`` + ``## {family_prefix}`` concatenated."""
        await self._ensure_loaded()
        async with self._lock:
            parts: list[str] = []
            core = self._sections.get("Core", "")
            if core:
                parts.append(core.strip())
            family = self._sections.get(family_prefix.value, "")
            if family:
                parts.append(family.strip())
            return "\n\n".join(parts)

    async def write_section(
        self, section: str, content: str, *, requester: FamilyPrefix
    ) -> None:
        """Update a section in character.md. Permission-checked.

        ``<Pr>`` can write any section; other families can write their own.
        """
        if not self._permissions.check(
            requester, PermissionAction.WRITE_CHARACTER, section
        ):
            raise PermissionError(
                f"{requester} lacks write permission for character section {section!r}"
            )

        await self._ensure_loaded()
        async with self._lock:
            self._sections[section] = content
            self._logger.action(
                f"character.md section '{section}' updated by {requester}"
            )
            await self._flush_unlocked()

    async def _flush_unlocked(self) -> None:
        """Write current sections back to character.md (caller holds lock)."""
        lines: list[str] = []
        # Write preamble first if it exists
        preamble = self._sections.get("_preamble", "")
        if preamble:
            lines.append(preamble.strip() + "\n\n")
        for header, body in self._sections.items():
            if header == "_preamble":
                continue
            lines.append(f"## {header}\n")
            lines.append(body.strip() + "\n\n")

        self._raw = "".join(lines)
        async with aiofiles.open(self._path, "w", encoding="utf-8") as f:
            await f.write(self._raw)

    def invalidate_cache(self) -> None:
        """Force next access to re-read from disk."""
        self._loaded = False
        self._sections = {}
        self._raw = ""
