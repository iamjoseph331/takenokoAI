"""TakenokoAI agent orchestrator and self-model manager."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiofiles
import yaml

from interface.bus import FamilyPrefix, MessageBus
from interface.character_model import CharacterModel
from interface.llm import LLMConfig, configure_api_keys
from interface.logging import ModuleLogger, setup_logging
from interface.markdown_utils import parse_markdown_sections
from interface.modules import MainModule
from interface.permissions import PermissionManager
from interface.prompt_assembler import PromptAssembler
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
        async with self._lock:
            if not self._path.exists():
                self._logger.action(f"self.md not found at {self._path}, starting empty")
                self._sections = {}
                return {}

            async with aiofiles.open(self._path, "r", encoding="utf-8") as f:
                content = await f.read()

            self._sections = parse_markdown_sections(content)
            self._logger.action(
                f"Loaded self.md: {len(self._sections)} sections"
            )
            return dict(self._sections)

    async def load_part(self, section: str) -> str:
        """Read a single section from self.md."""
        if not self._sections:
            await self.load_all()
        async with self._lock:
            return self._sections.get(section, "")

    async def write_part(
        self, section: str, content: str, *, requester: FamilyPrefix
    ) -> None:
        """Update a section in self.md. Permission-checked.

        Acquires the lock for both the in-memory update and the disk flush
        to prevent reads from seeing partially-written state.
        """
        from interface.permissions import PermissionAction

        if not self._permissions.check(
            requester, PermissionAction.WRITE_SELF_MD, section
        ):
            raise PermissionError(
                f"{requester} lacks WRITE_SELF_MD permission for section {section!r}"
            )

        async with self._lock:
            self._sections[section] = content
            self._logger.action(
                f"self.md section '{section}' updated by {requester}"
            )
            await self._flush_unlocked()

    async def _flush(self) -> None:
        """Write current sections back to self.md on disk (acquires lock)."""
        async with self._lock:
            await self._flush_unlocked()

    async def _flush_unlocked(self) -> None:
        """Write current sections back to self.md on disk (caller holds lock)."""
        lines: list[str] = []
        for header, body in self._sections.items():
            if header == "_preamble":
                lines.append(body.strip() + "\n\n")
                continue
            lines.append(f"## {header}\n")
            lines.append(body.strip() + "\n\n")

        async with aiofiles.open(self._path, "w", encoding="utf-8") as f:
            await f.write("".join(lines))


class TakenokoAgent:
    """Top-level orchestrator that boots and runs all five families.

    Boot sequence: config -> logging -> bus -> permissions -> self_model
                   -> character_model -> families (with prompt assemblers) -> start all.
    """

    def __init__(self, config_path: str = "admin/yamls/default.yaml") -> None:
        self._config_path = config_path
        self._config: dict[str, Any] = {}
        self._logger: ModuleLogger | None = None
        self._bus: MessageBus | None = None
        self._permissions: PermissionManager | None = None
        self._self_model: SelfModel | None = None
        self._character_model: CharacterModel | None = None
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

        api_key_envs = self._config.get("api_key_envs", {})
        configure_api_keys(api_key_envs, logger=self._logger)

        # 3. Bus (with per-family queue limits for backpressure)
        resources_cfg = self._config.get("resources", {})
        queue_limits = resources_cfg.get("queue_limits", {})
        self._bus = MessageBus(self._logger, queue_limits=queue_limits)

        # 4. Permissions
        self._permissions = PermissionManager(self._logger)

        # 5. Self-model
        self_model_path = agent_cfg.get("self_model_path", "self.md")
        self._self_model = SelfModel(
            self_model_path, self._permissions, self._logger
        )
        await self._self_model.load_all()

        # 6. Character model
        character_path = agent_cfg.get("character_path", "character.md")
        self._character_model = CharacterModel(
            character_path, self._permissions, self._logger
        )
        await self._character_model.load_all()

        # 7. Build families with prompt assemblers
        family_classes: dict[FamilyPrefix, type[MainModule]] = {
            FamilyPrefix.Re: ReactionModule,
            FamilyPrefix.Pr: PredictionModule,
            FamilyPrefix.Ev: EvaluationModule,
            FamilyPrefix.Me: MemorizationModule,
            FamilyPrefix.Mo: MotionModule,
        }

        for prefix, cls in family_classes.items():
            llm_config = self._build_llm_config(prefix)
            assembler = self._build_prompt_assembler(prefix)
            logger = ModuleLogger(prefix.value, "main")
            module = cls(
                bus=self._bus,
                logger=logger,
                llm_config=llm_config,
                permissions=self._permissions,
                prompt_assembler=assembler,
            )
            self._families[prefix] = module

        # 8. Wire family state callback into each module
        for module in self._families.values():
            module._family_state_fn = self.get_family_states

        # 9. Start all families
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
        )

    def _build_prompt_assembler(
        self, family_prefix: FamilyPrefix
    ) -> PromptAssembler:
        """Build a PromptAssembler for a given family from config."""
        families_cfg = self._config.get("families", {})
        family_cfg = families_cfg.get(family_prefix.value, {})
        identity_path = family_cfg.get(
            "identity_prompt",
            f"prompts/identity/{family_prefix.value.lower()}_identity.md",
        )
        rulebook_path = family_cfg.get(
            "rulebook",
            f"{family_prefix.value.lower()}/rulebook.md",
        )
        logger = ModuleLogger(family_prefix.value, "assembler")
        return PromptAssembler(
            family_prefix=family_prefix,
            identity_path=identity_path,
            self_model=self._self_model,
            rulebook_path=rulebook_path,
            character_model=self._character_model,
            logger=logger,
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

    def get_family_states(self) -> dict[str, str]:
        """Return a snapshot of all family states: {"Re": "IDLE", ...}."""
        return {
            prefix.value: str(module.state)
            for prefix, module in self._families.items()
        }
