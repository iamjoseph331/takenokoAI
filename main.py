"""TakenokoAI agent orchestrator and self-model manager."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiofiles
import yaml

from interface.bus import FamilyPrefix, MessageBus
from interface.llm import LLMConfig
from interface.logging import ModuleLogger, setup_logging
from interface.modules import MainModule
from interface.permissions import PermissionManager
from evaluation.ev_main_module import EvaluationModule
from memorization.me_main_module import MemorizationModule
from motion.mo_main_module import MotionModule
from prediction.pr_main_module import PredictionModule
from reaction.re_main_module import ReactionModule


class SelfModel:
    """Manages self.md — the agent's runtime self-model.

    Parses the file by ## Section headers. Each family owns its own section;
    <Pr> can write to any section.
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
        self._lock = asyncio.Lock()

    async def load_all(self) -> dict[str, str]:
        """Read self.md and parse into sections keyed by header name."""
        if not self._path.exists():
            self._logger.action(f"self.md not found at {self._path}, starting empty")
            self._sections = {}
            return {}

        async with aiofiles.open(self._path, "r", encoding="utf-8") as f:
            content = await f.read()

        self._sections = self._parse_sections(content)
        self._logger.action(
            f"Loaded self.md: {len(self._sections)} sections"
        )
        return dict(self._sections)

    async def load_part(self, section: str) -> str:
        """Read a single section from self.md."""
        if not self._sections:
            await self.load_all()
        return self._sections.get(section, "")

    async def write_part(
        self, section: str, content: str, *, requester: FamilyPrefix
    ) -> None:
        """Update a section in self.md. Permission-checked."""
        from interface.permissions import PermissionAction

        if not self._permissions.check(
            requester, PermissionAction.WRITE_SELF_MD, section
        ):
            raise PermissionError(
                f"{requester} lacks WRITE_SELF_MD permission for section {section!r}"
            )

        self._sections[section] = content
        self._logger.action(
            f"self.md section '{section}' updated by {requester}"
        )
        await self._flush()

    async def _flush(self) -> None:
        """Write current sections back to self.md on disk."""
        async with self._lock:
            lines: list[str] = []
            for header, body in self._sections.items():
                lines.append(f"## {header}\n")
                lines.append(body.strip() + "\n\n")

            async with aiofiles.open(self._path, "w", encoding="utf-8") as f:
                await f.write("".join(lines))

    @staticmethod
    def _parse_sections(content: str) -> dict[str, str]:
        """Split markdown content by ## headers into a dict."""
        sections: dict[str, str] = {}
        current_header: str | None = None
        current_lines: list[str] = []

        for line in content.splitlines(keepends=True):
            if line.startswith("## "):
                if current_header is not None:
                    sections[current_header] = "".join(current_lines)
                current_header = line[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_header is not None:
            sections[current_header] = "".join(current_lines)

        return sections


class TakenokoAgent:
    """Top-level orchestrator that boots and runs all five families.

    Boot sequence: config -> logging -> bus -> permissions -> self_model -> families -> start all.
    """

    def __init__(self, config_path: str = "admin/yamls/default.yaml") -> None:
        self._config_path = config_path
        self._config: dict[str, Any] = {}
        self._logger: ModuleLogger | None = None
        self._bus: MessageBus | None = None
        self._permissions: PermissionManager | None = None
        self._self_model: SelfModel | None = None
        self._families: dict[FamilyPrefix, MainModule] = {}

    async def start(self) -> None:
        """Boot the agent: load config, initialize infrastructure, start all families."""
        # 1. Config
        self._config = self._load_config()

        # 2. Logging
        agent_cfg = self._config.get("agent", {})
        setup_logging(
            log_dir=agent_cfg.get("log_dir", "logs"),
            level=getattr(logging, agent_cfg.get("log_level", "DEBUG")),
        )
        self._logger = ModuleLogger("SYS", "agent")
        self._logger.action("TakenokoAI booting...")

        # 3. Bus
        self._bus = MessageBus(self._logger)

        # 4. Permissions
        self._permissions = PermissionManager(self._logger)

        # 5. Self-model
        self._self_model = SelfModel(
            "self.md", self._permissions, self._logger
        )
        await self._self_model.load_all()

        # 6. Build families
        family_classes: dict[FamilyPrefix, type[MainModule]] = {
            FamilyPrefix.Re: ReactionModule,
            FamilyPrefix.Pr: PredictionModule,
            FamilyPrefix.Ev: EvaluationModule,
            FamilyPrefix.Me: MemorizationModule,
            FamilyPrefix.Mo: MotionModule,
        }

        for prefix, cls in family_classes.items():
            llm_config = self._build_llm_config(prefix)
            logger = ModuleLogger(prefix.value, "main")
            module = cls(
                bus=self._bus,
                logger=logger,
                llm_config=llm_config,
                permissions=self._permissions,
            )
            self._families[prefix] = module

        # 7. Start all families
        for module in self._families.values():
            await module.start()

        self._logger.action(
            f"TakenokoAI started: {len(self._families)} families active"
        )

    def _load_config(self) -> dict[str, Any]:
        """Load YAML configuration from disk."""
        path = Path(self._config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _build_llm_config(self, family_prefix: FamilyPrefix) -> LLMConfig:
        """Build an LLMConfig from the YAML config for a given family."""
        families_cfg = self._config.get("families", {})
        family_cfg = families_cfg.get(family_prefix.value, {})
        return LLMConfig(
            model_name=family_cfg.get("model", "gpt-4o"),
            temperature=family_cfg.get("temperature", 0.7),
            max_tokens=family_cfg.get("max_tokens", 4096),
            system_prompt_path=family_cfg.get("prompt"),
        )

    async def run(self) -> None:
        """Run all family message loops concurrently."""
        if not self._families:
            raise RuntimeError("Agent not started. Call start() first.")

        async with asyncio.TaskGroup() as tg:
            for module in self._families.values():
                tg.create_task(module._message_loop())

    async def stop(self) -> None:
        """Stop all families and flush the self-model to disk."""
        if self._logger:
            self._logger.action("TakenokoAI shutting down...")

        for module in self._families.values():
            await module.stop()

        if self._self_model:
            await self._self_model._flush()

        if self._logger:
            self._logger.action("TakenokoAI stopped")

    async def inject_input(self, input_data: dict[str, Any]) -> None:
        """External entry point — feed input to the Reaction module."""
        re_module = self._families.get(FamilyPrefix.Re)
        if re_module is None:
            raise RuntimeError("Reaction module not initialized")
        if not isinstance(re_module, ReactionModule):
            raise TypeError("Expected ReactionModule")
        await re_module.perceive(input_data)

    def get_family(self, prefix: FamilyPrefix) -> MainModule:
        """Get a family module by its prefix."""
        if prefix not in self._families:
            raise KeyError(f"Family {prefix} not found")
        return self._families[prefix]
