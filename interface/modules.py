"""Base module hierarchy: BaseModule, MainModule, SubModule.

Every family module inherits from MainModule. Sub-modules inherit from SubModule
and attach to their parent MainModule at runtime via the self-registration protocol.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Optional

from interface.bus import BusMessage, CognitionPath, FamilyPrefix, MessageBus
from interface.llm import LLMClient, LLMConfig
from interface.logging import ModuleLogger
from interface.permissions import PermissionAction, PermissionManager


class ModuleState(StrEnum):
    """Built-in module states."""

    IDLE = "IDLE"
    THINKING = "THINKING"


class BaseModule(ABC):
    """Abstract base for all modules in TakenokoAI.

    Provides bus registration, LLM client, logging, and the core
    send_message / think interface.
    """

    def __init__(
        self,
        family_prefix: FamilyPrefix,
        name: str,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
    ) -> None:
        self.family_prefix = family_prefix
        self.name = name
        self._bus = bus
        self._logger = logger
        self._permissions = permissions
        self._llm = LLMClient(llm_config, logger)
        self._queue = bus.register(self.qualified_name)

    @property
    def qualified_name(self) -> str:
        """Fully qualified name: e.g. 'Re.main'."""
        return f"{self.family_prefix.value}.{self.name}"

    @abstractmethod
    async def start(self) -> None:
        """Start the module's processing loop."""
        raise NotImplementedError("Subclasses must implement start()")

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the module."""
        raise NotImplementedError("Subclasses must implement stop()")

    async def send_message(
        self,
        receiver: FamilyPrefix,
        body: Any,
        path: CognitionPath,
        *,
        context: str = "",
        parent_message_id: str | None = None,
        resources: dict[str, Any] | None = None,
    ) -> str:
        """Build and send a BusMessage, returning the new message_id."""
        raise NotImplementedError("send_message requires MainModule context")

    async def think(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Call the LLM and log the interaction."""
        self._logger.thought(f"Thinking... ({len(messages)} messages)")
        result = await self._llm.complete(messages, **kwargs)
        self._logger.thought(f"Thought complete: {len(result)} chars")
        return result


class MainModule(BaseModule):
    """Base class for family main modules.

    Owns the message counter, state machine, sub-module registry,
    and the async API surface exposed to other families.
    """

    def __init__(
        self,
        family_prefix: FamilyPrefix,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
    ) -> None:
        super().__init__(family_prefix, "main", bus, logger, llm_config, permissions)
        self._message_counter: int = 0
        self._state: ModuleState | str = ModuleState.IDLE
        self._custom_states: set[str] = set()
        self._submodules: dict[str, SubModule] = {}
        self._task_queue: asyncio.Queue[Any] = asyncio.Queue()
        self._running: bool = False

    # ── Message ID generation ──

    def next_message_id(self, path: CognitionPath) -> str:
        """Generate the next sequential message ID for this family."""
        self._message_counter += 1
        return MessageBus.make_message_id(
            self.family_prefix, self._message_counter, path
        )

    async def send_message(
        self,
        receiver: FamilyPrefix,
        body: Any,
        path: CognitionPath,
        *,
        context: str = "",
        parent_message_id: str | None = None,
        resources: dict[str, Any] | None = None,
    ) -> str:
        """Build, validate, and send a message on the bus."""
        msg_id = self.next_message_id(path)

        if not MessageBus.validate_route(self.family_prefix, receiver, path):
            self._logger.action(
                f"WARNING: Route {self.family_prefix}->{receiver} not standard "
                f"for path {path}, sending anyway"
            )

        message = BusMessage(
            message_id=msg_id,
            parent_message_id=parent_message_id,
            timecode=MessageBus.now(),
            context=context,
            body=body,
            sender=self.family_prefix,
            receiver=receiver,
            resources=resources,
        )
        await self._bus.send(message)
        return msg_id

    # ── Sub-module management (申告制) ──

    def register_submodule(self, sub: SubModule) -> None:
        """Register a sub-module under this main module."""
        self._submodules[sub.name] = sub
        self._logger.action(
            f"Sub-module registered: {sub.name} — {sub.description}"
        )

    def unregister_submodule(self, name: str) -> None:
        """Remove a sub-module."""
        if name in self._submodules:
            self._bus.unregister(self._submodules[name].qualified_name)
            del self._submodules[name]
            self._logger.action(f"Sub-module unregistered: {name}")

    def list_submodules(self) -> dict[str, dict[str, str]]:
        """Return capability descriptors for all registered sub-modules."""
        return {name: sub.announce() for name, sub in self._submodules.items()}

    # ── State management ──

    @property
    def state(self) -> ModuleState | str:
        return self._state

    async def set_state(self, new_state: ModuleState | str) -> None:
        """Update module state and broadcast the change."""
        old_state = self._state
        self._state = new_state
        if isinstance(new_state, str) and new_state not in ModuleState.__members__:
            self._custom_states.add(new_state)
        self._logger.action(f"State: {old_state} -> {new_state}")

    # ── Async API surface (exposed to other families) ──

    async def get_resources(self) -> dict[str, Any]:
        """Return current resource levels of this family."""
        raise NotImplementedError("get_resources")

    async def get_queue_info(self) -> dict[str, Any]:
        """Return task queue statistics."""
        return {
            "length": self._task_queue.qsize(),
            "max_length": self._task_queue.maxsize,
        }

    async def change_prompt(self, path: str, requester: FamilyPrefix) -> None:
        """Change the system prompt file. Requires permission."""
        if not self._permissions.check(
            requester, PermissionAction.CHANGE_PROMPT, self.family_prefix.value
        ):
            raise PermissionError(
                f"{requester} lacks CHANGE_PROMPT on {self.family_prefix}"
            )
        self._llm.update_config(system_prompt_path=path)
        await self._llm.reload_system_prompt()

    async def change_model(self, model_name: str, requester: FamilyPrefix) -> None:
        """Change the LLM model. Requires permission."""
        if not self._permissions.check(
            requester, PermissionAction.CHANGE_MODEL, self.family_prefix.value
        ):
            raise PermissionError(
                f"{requester} lacks CHANGE_MODEL on {self.family_prefix}"
            )
        self._llm.update_config(model_name=model_name)

    async def restart(self, requester: FamilyPrefix) -> None:
        """Restart this module. Requires permission."""
        if not self._permissions.check(
            requester, PermissionAction.RESTART_MODULE, self.family_prefix.value
        ):
            raise PermissionError(
                f"{requester} lacks RESTART_MODULE on {self.family_prefix}"
            )
        await self.stop()
        await self.start()

    async def get_limits(self) -> dict[str, Any]:
        """Return family limits (max context tokens, etc.)."""
        raise NotImplementedError("get_limits")

    async def pause_and_answer(
        self, question: str, requester: FamilyPrefix
    ) -> str:
        """Pause current work and answer a question from another family."""
        raise NotImplementedError("pause_and_answer")

    # ── Message loop ──

    @abstractmethod
    async def _message_loop(self) -> None:
        """Main processing loop — each family implements its own."""
        raise NotImplementedError("Subclasses must implement _message_loop()")

    async def start(self) -> None:
        """Start the message processing loop."""
        self._running = True
        self._logger.action(f"{self.qualified_name} started")

    async def stop(self) -> None:
        """Signal the module to stop."""
        self._running = False
        self._logger.action(f"{self.qualified_name} stopped")


class SubModule(BaseModule):
    """Base class for family sub-modules.

    Sub-modules attach to a parent MainModule and announce their
    capabilities via the self-registration protocol (申告制).
    """

    def __init__(
        self,
        parent: MainModule,
        name: str,
        description: str,
        llm_config: LLMConfig,
    ) -> None:
        super().__init__(
            family_prefix=parent.family_prefix,
            name=name,
            bus=parent._bus,
            logger=ModuleLogger(parent.family_prefix.value, name),
            llm_config=llm_config,
            permissions=parent._permissions,
        )
        self._parent = parent
        self.description = description
        parent.register_submodule(self)

    def announce(self) -> dict[str, str]:
        """Return a capability descriptor for self.md registration."""
        return {
            "name": self.name,
            "family": self.family_prefix.value,
            "description": self.description,
            "qualified_name": self.qualified_name,
        }

    @abstractmethod
    async def handle_message(self, message: BusMessage) -> Optional[BusMessage]:
        """Process an incoming message. Return a response message or None."""
        raise NotImplementedError("Subclasses must implement handle_message()")

    async def start(self) -> None:
        self._logger.action(f"Sub-module {self.qualified_name} started")

    async def stop(self) -> None:
        self._logger.action(f"Sub-module {self.qualified_name} stopped")
