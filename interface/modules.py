"""Base module hierarchy: BaseModule, MainModule, SubModule.

Every family module inherits from MainModule. Sub-modules inherit from SubModule
and attach to their parent MainModule at runtime via the self-registration protocol.
"""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Optional

from interface.bus import (
    BusMessage,
    CognitionPath,
    FamilyPrefix,
    MessageBus,
    QueueFullSignal,
)
from interface.llm import CompletionFn, LLMClient, LLMConfig
from interface.logging import ModuleLogger
from interface.permissions import PermissionAction, PermissionManager
from interface.prompt_assembler import PromptAssembler


class ModuleState(StrEnum):
    """Built-in module states."""

    IDLE = "IDLE"
    THINKING = "THINKING"


IDLE_TIMEOUT_S = 1.0


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
        prompt_assembler: PromptAssembler | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        self.family_prefix = family_prefix
        self.name = name
        self._bus = bus
        self._logger = logger
        self._permissions = permissions
        self._llm = LLMClient(
            llm_config, logger,
            prompt_assembler=prompt_assembler,
            completion_fn=completion_fn,
        )
        self._queue = bus.register(self.qualified_name)

    @property
    def qualified_name(self) -> str:
        """Fully qualified name: e.g. 'Re.main'."""
        return f"{self.family_prefix.value}.{self.name}"

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError("Subclasses must implement start()")

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError("Subclasses must implement stop()")

    async def send_message(
        self,
        receiver: FamilyPrefix,
        body: Any,
        path: CognitionPath,
        *,
        context: str = "",
        parent_message_id: str | None = None,
        trace_id: str = "",
        resources: dict[str, Any] | None = None,
    ) -> str:
        raise NotImplementedError("send_message requires MainModule context")

    async def think(
        self,
        messages: list[dict[str, str]],
        *,
        temperature_override: float | None = None,
        **kwargs: Any,
    ) -> str:
        """Call the LLM and log the interaction."""
        self._logger.thought(f"Thinking... ({len(messages)} messages)")
        result = await self._llm.complete(
            messages, temperature_override=temperature_override, **kwargs
        )
        self._logger.thought(f"Thought complete: {len(result)} chars")
        return result


class MainModule(BaseModule):
    """Base class for family main modules.

    Owns the message counter, state machine, sub-module registry,
    and the async API surface exposed to other families.

    Provides a standard _message_loop() that subclasses extend via
    _handle_message() (for processing) and _on_idle() (for S-path).
    """

    def __init__(
        self,
        family_prefix: FamilyPrefix,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
        prompt_assembler: PromptAssembler | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            family_prefix, "main", bus, logger, llm_config, permissions,
            prompt_assembler=prompt_assembler,
            completion_fn=completion_fn,
        )
        self._message_counter: int = 0
        self._state: ModuleState | str = ModuleState.IDLE
        self._custom_states: set[str] = set()
        self._submodules: dict[str, SubModule] = {}
        self._task_queue: asyncio.Queue[Any] = asyncio.Queue()
        self._running: bool = False
        self._pause_event: asyncio.Event = asyncio.Event()
        self._pause_event.set()  # not paused by default
        self._pause_response_queue: asyncio.Queue[str] = asyncio.Queue()

    # ── Message ID generation ──

    def next_message_id(self, path: CognitionPath) -> str:
        """Generate the next sequential message ID for this family."""
        self._message_counter += 1
        return MessageBus.make_message_id(
            self.family_prefix, self._message_counter, path
        )

    @staticmethod
    def _generate_trace_id() -> str:
        return uuid.uuid4().hex[:12]

    async def send_message(
        self,
        receiver: FamilyPrefix,
        body: Any,
        path: CognitionPath,
        *,
        context: str = "",
        parent_message_id: str | None = None,
        trace_id: str = "",
        resources: dict[str, Any] | None = None,
        summary: str = "",
    ) -> str:
        """Build, validate, and send a message on the bus.

        Returns the message_id. If the receiver's queue is full, returns
        the message_id prefixed with "FULL:" as a backpressure signal.
        """
        msg_id = self.next_message_id(path)

        if not trace_id:
            trace_id = self._generate_trace_id()

        if not MessageBus.validate_route(self.family_prefix, receiver, path):
            self._logger.action(
                f"WARNING: Route {self.family_prefix}->{receiver} not standard "
                f"for path {path}, sending anyway (advisory)"
            )

        message = BusMessage(
            message_id=msg_id,
            parent_message_id=parent_message_id,
            trace_id=trace_id,
            timecode=MessageBus.now(),
            context=context,
            body=body,
            sender=self.family_prefix,
            receiver=receiver,
            resources=resources,
            summary=summary,
        )
        result = await self._bus.send(message)

        if isinstance(result, QueueFullSignal):
            self._logger.action(
                f"Send failed (queue full): {msg_id} -> {receiver} "
                f"(queue_size={result.queue_size})"
            )
            return f"FULL:{msg_id}"

        return msg_id

    async def send_ack(
        self, original_message: BusMessage, *, queue_size: int | None = None
    ) -> None:
        """Send an acknowledgment back to the sender of a message."""
        ack_id = MessageBus.make_ack_id(original_message.message_id)
        ack = BusMessage(
            message_id=ack_id,
            parent_message_id=original_message.message_id,
            trace_id=original_message.trace_id,
            timecode=MessageBus.now(),
            context="ack",
            body={
                "ack": True,
                "queue_size": queue_size if queue_size is not None else self._queue.qsize(),
            },
            sender=self.family_prefix,
            receiver=original_message.sender,
            is_ack=True,
        )
        await self._bus.send(ack)

    # ── Sub-module management (申告制) ──

    def register_submodule(self, sub: SubModule) -> None:
        self._submodules[sub.name] = sub
        self._logger.action(
            f"Sub-module registered: {sub.name} — {sub.description}"
        )

    def unregister_submodule(self, name: str) -> None:
        if name in self._submodules:
            self._bus.unregister(self._submodules[name].qualified_name)
            del self._submodules[name]
            self._logger.action(f"Sub-module unregistered: {name}")

    def list_submodules(self) -> dict[str, dict[str, str]]:
        return {name: sub.announce() for name, sub in self._submodules.items()}

    # ── State management ──

    @property
    def state(self) -> ModuleState | str:
        return self._state

    async def set_state(self, new_state: ModuleState | str) -> None:
        old_state = self._state
        self._state = new_state
        if isinstance(new_state, str) and new_state not in ModuleState.__members__:
            self._custom_states.add(new_state)
        self._logger.action(f"State: {old_state} -> {new_state}")

    # ── Async API surface ──

    async def get_resources(self) -> dict[str, Any]:
        return {"state": str(self._state), "queue_size": self._queue.qsize()}

    async def get_queue_info(self) -> dict[str, Any]:
        return {
            "length": self._task_queue.qsize(),
            "max_length": self._task_queue.maxsize,
        }

    async def change_prompt(self, requester: FamilyPrefix) -> None:
        if not self._permissions.check(
            requester, PermissionAction.CHANGE_PROMPT, self.family_prefix.value
        ):
            raise PermissionError(
                f"{requester} lacks CHANGE_PROMPT on {self.family_prefix}"
            )
        await self._llm.reload_system_prompt()

    async def change_model(self, model_name: str, requester: FamilyPrefix) -> None:
        if not self._permissions.check(
            requester, PermissionAction.CHANGE_MODEL, self.family_prefix.value
        ):
            raise PermissionError(
                f"{requester} lacks CHANGE_MODEL on {self.family_prefix}"
            )
        self._llm.update_config(model_name=model_name)

    async def restart(self, requester: FamilyPrefix) -> None:
        if not self._permissions.check(
            requester, PermissionAction.RESTART_MODULE, self.family_prefix.value
        ):
            raise PermissionError(
                f"{requester} lacks RESTART_MODULE on {self.family_prefix}"
            )
        await self.stop()
        await self.start()

    async def get_limits(self) -> dict[str, Any]:
        return {
            "max_tokens": self._llm.config.max_tokens,
            "model": self._llm.config.model_name,
            "timeout_s": self._llm.config.timeout_s,
        }

    async def pause_and_answer(
        self, question: str, requester: FamilyPrefix
    ) -> str:
        """Pause this module's processing loop, send the question to the
        LLM with current context, and return the answer.

        The module resumes normal processing after answering.
        """
        self._logger.action(
            f"pause_and_answer from {requester}: {question[:80]}..."
        )
        was_paused = not self._pause_event.is_set()
        self._pause_event.clear()  # pause processing

        try:
            broadcasts = self._bus.get_recent_broadcasts(5)
            broadcast_text = "\n".join(
                f"- [{b.sender}] {b.summary}" for b in broadcasts
            ) if broadcasts else "(none)"

            context_msg = (
                f"You are being asked a question by the operator ({requester}).\n"
                f"Your current state: {self._state}\n"
                f"Queue depth: {self._queue.qsize()}\n"
                f"Recent broadcasts:\n{broadcast_text}\n\n"
                f"Question: {question}\n\n"
                f"Answer concisely and directly."
            )
            messages = [{"role": "user", "content": context_msg}]
            answer = await self.think(messages)
            return answer
        finally:
            if not was_paused:
                self._pause_event.set()  # resume

    # ── Broadcast context helper ──

    def _build_broadcast_context(self) -> str:
        """Build a string of recent broadcasts for inclusion in LLM context."""
        broadcasts = self._bus.get_recent_broadcasts(5)
        if not broadcasts:
            return ""
        lines = [f"[{b.sender}] {b.summary}" for b in broadcasts]
        return "Recent activity:\n" + "\n".join(lines)

    # ── Message loop (template method pattern) ──

    async def _message_loop(self) -> None:
        """Standard message loop: receive → ack → handle → idle.

        Subclasses override _handle_message() for processing logic
        and optionally _on_idle() for S-path behavior.
        """
        self._logger.action(f"_message_loop started for {self.qualified_name}")
        while self._running:
            await self._pause_event.wait()
            try:
                message = await self._bus.receive(
                    self.qualified_name, timeout=IDLE_TIMEOUT_S
                )
            except (TimeoutError, asyncio.TimeoutError):
                await self._on_idle()
                continue

            if message.is_ack:
                self._logger.bus_message(
                    f"ACK received: {message.message_id}"
                )
                continue

            await self.send_ack(message)
            await self.set_state(ModuleState.THINKING)
            try:
                await self._handle_message(message)
            except Exception as e:
                self._logger.action(
                    f"Error handling message {message.message_id}: {e}",
                    data={"error": str(e)},
                )
            await self.set_state(ModuleState.IDLE)

    @abstractmethod
    async def _handle_message(self, message: BusMessage) -> None:
        """Process a single incoming message. Subclasses must implement."""
        raise NotImplementedError

    async def _on_idle(self) -> None:
        """Called when no message arrives within the timeout.

        Default: do nothing. Override for S-path behavior (Stage 2).
        """
        pass

    async def start(self) -> None:
        self._running = True
        self._logger.action(f"{self.qualified_name} started")

    async def stop(self) -> None:
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
        return {
            "name": self.name,
            "family": self.family_prefix.value,
            "description": self.description,
            "qualified_name": self.qualified_name,
        }

    @abstractmethod
    async def handle_message(self, message: BusMessage) -> Optional[BusMessage]:
        raise NotImplementedError("Subclasses must implement handle_message()")

    async def start(self) -> None:
        self._logger.action(f"Sub-module {self.qualified_name} started")

    async def stop(self) -> None:
        self._logger.action(f"Sub-module {self.qualified_name} stopped")
