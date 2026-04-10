"""Base module hierarchy: BaseModule, MainModule, SubModule.

Every family module inherits from MainModule. Sub-modules inherit from SubModule
and attach to their parent MainModule at runtime via the self-registration protocol.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Callable, Optional

from interface.bus import (
    BusMessage,
    CognitionPath,
    FamilyPrefix,
    MessageBus,
    QueueFullPolicy,
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
        summary: str = "",
    ) -> str:
        raise NotImplementedError("send_message requires MainModule or SubModule")

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
        self._state: ModuleState | str = ModuleState.IDLE
        self._custom_states: set[str] = set()
        self._submodules: dict[str, SubModule] = {}
        self._submodule_registry: dict[str, dict[str, Any]] = {}
        self._task_queue: asyncio.Queue[Any] = asyncio.Queue()
        self._running: bool = False
        self._pause_event: asyncio.Event = asyncio.Event()
        self._pause_event.set()  # not paused by default
        self._pause_response_queue: asyncio.Queue[str] = asyncio.Queue()

        # Family state query callback (set by orchestrator after boot)
        self._family_state_fn: Callable[[], dict[str, str]] | None = None

        # S-path idle detection
        self._last_activity_time: float = time.monotonic()
        self._idle_streak: int = 0
        self._sleep_until: float = 0.0
        self._idle_nudge_threshold: float = 5.0   # seconds before first nudge
        self._max_idle_streak: int = 5             # consecutive nudges before forced sleep
        self._self_message_budget: int = 3         # max self-messages per budget window
        self._self_message_count: int = 0
        self._budget_window_start: float = 0.0
        self._budget_window_seconds: float = 60.0

    # ── Message ID generation ──

    def next_message_id(self, path: CognitionPath) -> str:
        """Generate the next sequential message ID for this family.

        Delegates to the bus's shared per-family counter so that
        MainModule and SubModule IDs never collide.
        """
        return self._bus.next_message_id(self.family_prefix, path)

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
        """Register a submodule by direct reference (legacy path).

        Prefer bus-based registration via SubModule.start() for new code.
        Scheduled for removal in Stage 2.
        """
        self._submodules[sub.name] = sub
        self._logger.action(
            f"Sub-module registered: {sub.name} — {sub.description}"
        )

    def _handle_sub_registration(self, body: dict[str, Any]) -> None:
        """Process a bus-based submodule registration message."""
        name = body["name"]
        self._submodule_registry[name] = {
            "qualified_name": body["qualified_name"],
            "description": body["description"],
            "capabilities": body.get("capabilities", []),
        }
        self._logger.action(
            f"Sub-module registered via bus: {name} — {body.get('description', '')}"
        )

    def unregister_submodule(self, name: str) -> None:
        if name in self._submodules:
            self._bus.unregister(self._submodules[name].qualified_name)
            del self._submodules[name]
            self._logger.action(f"Sub-module unregistered: {name}")
        if name in self._submodule_registry:
            qn = self._submodule_registry[name].get("qualified_name", "")
            if qn:
                self._bus.unregister(qn)
            del self._submodule_registry[name]
            self._logger.action(f"Sub-module unregistered (bus): {name}")

    def list_submodules(self) -> dict[str, dict[str, Any]]:
        """Return capability descriptors for all registered sub-modules."""
        result: dict[str, dict[str, Any]] = {}
        for name, sub in self._submodules.items():
            result[name] = sub.announce()
        for name, info in self._submodule_registry.items():
            if name not in result:
                result[name] = info
        return result

    def find_capability(self, capability_name: str) -> str | None:
        """Find the submodule that provides a given capability.

        Returns the submodule's qualified_name, or None if not found.
        Checks both direct-reference and bus-registered submodules.
        """
        for sub in self._submodules.values():
            if hasattr(sub, "capabilities"):
                for cap in sub.capabilities():
                    if cap.name == capability_name:
                        return sub.qualified_name
        for info in self._submodule_registry.values():
            for cap in info.get("capabilities", []):
                cap_name = cap.get("name") if isinstance(cap, dict) else cap.name
                if cap_name == capability_name:
                    return info["qualified_name"]
        return None

    def list_capabilities(self) -> list[dict[str, Any]]:
        """Return a flat list of all capabilities across all submodules."""
        caps: list[dict[str, Any]] = []
        for sub in self._submodules.values():
            if hasattr(sub, "capabilities"):
                for cap in sub.capabilities():
                    entry = cap.to_dict()
                    entry["submodule"] = sub.name
                    entry["qualified_name"] = sub.qualified_name
                    caps.append(entry)
        for name, info in self._submodule_registry.items():
            for cap in info.get("capabilities", []):
                entry = dict(cap) if isinstance(cap, dict) else cap.to_dict()
                entry["submodule"] = name
                entry["qualified_name"] = info["qualified_name"]
                caps.append(entry)
        return caps

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

    async def request_state_change(
        self, new_state: ModuleState | str, requester: FamilyPrefix
    ) -> None:
        """Change this module's state. Permission-checked (SET_STATE)."""
        if not self._permissions.check(
            requester, PermissionAction.SET_STATE, self.family_prefix.value
        ):
            raise PermissionError(
                f"{requester} lacks SET_STATE permission on {self.family_prefix}"
            )
        await self.set_state(new_state)
        self._logger.action(
            f"State changed to {new_state} by {requester}"
        )

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

    # ── Context helpers ──

    def _get_family_states(self) -> dict[str, str]:
        """Query all family states via the orchestrator callback."""
        if self._family_state_fn is not None:
            return self._family_state_fn()
        return {self.family_prefix.value: str(self._state)}

    def _build_broadcast_context(self) -> str:
        """Build a string of recent broadcasts + family states for LLM context."""
        parts: list[str] = []

        broadcasts = self._bus.get_recent_broadcasts(5)
        if broadcasts:
            lines = [f"[{b.sender}] {b.summary}" for b in broadcasts]
            parts.append("Recent activity:\n" + "\n".join(lines))

        states = self._get_family_states()
        if states:
            state_str = ", ".join(f"{k}={v}" for k, v in states.items())
            parts.append(f"Family states: {state_str}")

        return "\n".join(parts)

    # ── Message loop (template method pattern) ──

    async def _message_loop(self) -> None:
        """Standard message loop: receive → ack → handle → idle.

        Subclasses override _handle_message() for processing logic
        and optionally _on_idle() for S-path behavior.

        Uses adaptive timeout: 1s when active, 5s when idle (saves CPU).
        """
        self._logger.action(f"_message_loop started for {self.qualified_name}")
        self._last_activity_time = time.monotonic()
        while self._running:
            await self._pause_event.wait()
            timeout = 5.0 if self._idle_streak > 0 else IDLE_TIMEOUT_S
            try:
                message = await self._bus.receive(
                    self.qualified_name, timeout=timeout
                )
            except (TimeoutError, asyncio.TimeoutError):
                await self._handle_idle_tick()
                continue

            if message.is_ack:
                self._logger.bus_message(
                    f"ACK received: {message.message_id}"
                )
                continue

            # Real message — reset idle state
            self._last_activity_time = time.monotonic()
            self._idle_streak = 0

            await self.send_ack(message)

            # Intercept bus-based submodule registration
            if (
                isinstance(message.body, dict)
                and message.body.get("_sub_register")
            ):
                self._handle_sub_registration(message.body)
                continue

            # Intercept state change requests (e.g. from Ev)
            if (
                isinstance(message.body, dict)
                and message.body.get("_set_state")
            ):
                new_state = message.body.get("new_state", "IDLE")
                try:
                    await self.request_state_change(new_state, message.sender)
                except PermissionError as e:
                    self._logger.action(f"State change denied: {e}")
                continue

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

    async def _handle_idle_tick(self) -> None:
        """Called when no message arrives within the timeout.

        Implements S-path idle detection with budgeting:
        - Waits until idle_nudge_threshold before first nudge
        - Limits self-messages per budget window
        - Forces sleep after max_idle_streak consecutive nudges
        """
        now = time.monotonic()
        idle_duration = now - self._last_activity_time

        # Skip if sleeping
        if now < self._sleep_until:
            return

        # Skip if below threshold
        if idle_duration < self._idle_nudge_threshold:
            return

        # Reset budget window if expired
        if now - self._budget_window_start > self._budget_window_seconds:
            self._self_message_count = 0
            self._budget_window_start = now

        # Skip if budget exhausted
        if self._self_message_count >= self._self_message_budget:
            return

        # Forced sleep after max streak
        if self._idle_streak >= self._max_idle_streak:
            self._sleep_until = now + self._budget_window_seconds
            self._idle_streak = 0
            self._logger.action(
                f"Forced sleep for {self._budget_window_seconds}s "
                f"after {self._max_idle_streak} idle nudges"
            )
            return

        self._idle_streak += 1
        self._self_message_count += 1

        # Call the overridable idle hook
        await self._on_idle(idle_duration)

    async def _on_idle(self, idle_duration: float) -> None:
        """Called when idle detection triggers.

        Override in subclasses for S-path behavior (self-directed thought).
        Default: log and do nothing.

        Args:
            idle_duration: Seconds since last real message was processed.
        """
        self._logger.action(
            f"Idle nudge #{self._idle_streak} ({idle_duration:.1f}s idle)"
        )

    async def start(self) -> None:
        self._running = True
        self._logger.action(f"{self.qualified_name} started")

    async def stop(self) -> None:
        self._running = False
        self._logger.action(f"{self.qualified_name} stopped")


class SubModule(BaseModule):
    """Base class for family sub-modules.

    Sub-modules are decoupled from MainModule and depend only on interfaces
    (bus, logger, permissions, llm). They communicate with their parent
    main module and other families exclusively through the message bus.

    Registration follows the 申告制 (self-registration protocol): on start(),
    the submodule sends a registration message to its parent's bus queue.

    Each submodule declares capabilities via the capabilities() method.
    Other modules discover and invoke these through a standardized interface.

    To add a capability named "foo":
      1. Include Capability(name="foo", ...) in capabilities()
      2. Implement async def _invoke_foo(self, params: dict) -> dict
    """

    def __init__(
        self,
        family_prefix: FamilyPrefix,
        name: str,
        description: str,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
        policy: QueueFullPolicy = QueueFullPolicy.WAIT,
        max_retries: int = 3,
        prompt_assembler: PromptAssembler | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            family_prefix=family_prefix,
            name=name,
            bus=bus,
            logger=logger,
            llm_config=llm_config,
            permissions=permissions,
            prompt_assembler=prompt_assembler,
            completion_fn=completion_fn,
        )
        self.description = description
        self._policy = policy
        self._max_retries = max_retries

    # ── Capability system ──

    @abstractmethod
    def capabilities(self) -> list:
        """Declare the capabilities this submodule provides.

        Returns a list of Capability objects. Each capability maps
        to an _invoke_{name} method on this submodule.
        """
        raise NotImplementedError("Subclasses must declare capabilities()")

    async def invoke(
        self, capability_name: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Invoke a capability by name.

        Dispatches to _invoke_{capability_name}(params). Returns a result
        dict with at least {"status": "ok"|"error"}.
        """
        handler = getattr(self, f"_invoke_{capability_name}", None)
        if handler is None:
            return {
                "status": "error",
                "reason": f"Unknown capability: {capability_name}",
            }
        try:
            return await handler(params or {})
        except Exception as e:
            self._logger.action(
                f"Capability {capability_name} failed: {type(e).__name__}: {e}"
            )
            return {"status": "error", "reason": f"{type(e).__name__}: {e}"}

    def announce(self) -> dict[str, Any]:
        """Return a capability descriptor for self.md registration."""
        return {
            "name": self.name,
            "family": self.family_prefix.value,
            "description": self.description,
            "qualified_name": self.qualified_name,
            "capabilities": [c.to_dict() for c in self.capabilities()],
        }

    # ── Message sending with QueueFullPolicy ──

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

        Uses the bus's shared per-family counter for message ID generation.
        Applies QueueFullPolicy when the receiver's queue is full.
        """
        msg_id = self._bus.next_message_id(self.family_prefix, path)

        if not trace_id:
            trace_id = uuid.uuid4().hex[:12]

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
            return await self._apply_policy(message)

        return msg_id

    async def _apply_policy(self, message: BusMessage) -> str:
        """Handle a full queue according to the configured policy."""
        if self._policy == QueueFullPolicy.DROP:
            self._logger.action(
                f"DROPPED (policy=DROP): {message.message_id} -> {message.receiver}"
            )
            return f"DROPPED:{message.message_id}"

        elif self._policy == QueueFullPolicy.RETRY:
            for attempt in range(self._max_retries):
                await asyncio.sleep(0.1 * (2 ** attempt))
                result = await self._bus.send(message)
                if not isinstance(result, QueueFullSignal):
                    return message.message_id
            self._logger.action(
                f"DROPPED (policy=RETRY, {self._max_retries} attempts): "
                f"{message.message_id} -> {message.receiver}"
            )
            return f"DROPPED:{message.message_id}"

        else:  # WAIT
            attempt = 0
            while True:
                await asyncio.sleep(0.1 * (2 ** min(attempt, 5)))
                result = await self._bus.send(message)
                if not isinstance(result, QueueFullSignal):
                    return message.message_id
                attempt += 1

    # ── Message handling ──

    async def handle_message(self, message: BusMessage) -> Optional[dict[str, Any]]:
        """Process an incoming message.

        Default implementation routes capability invocations:
          {"capability": "name", "params": {...}} -> invoke(name, params)

        Also supports legacy action format:
          {"action": "name", ...} -> invoke(name, remaining_body)

        Subclasses can override for custom message handling.
        """
        body = message.body if isinstance(message.body, dict) else {}

        if "capability" in body:
            result = await self.invoke(body["capability"], body.get("params", {}))
            return result

        if "action" in body:
            action = body["action"]
            params = {k: v for k, v in body.items() if k != "action"}
            result = await self.invoke(action, params)
            return result

        return None

    # ── Registration ──

    async def _register_via_bus(self) -> str:
        """Send a registration message to the parent main module via the bus.

        This is the bus-based 申告制 (self-registration protocol).
        """
        return await self.send_message(
            receiver=self.family_prefix,
            body={
                "_sub_register": True,
                "name": self.name,
                "description": self.description,
                "qualified_name": self.qualified_name,
                "capabilities": [c.to_dict() for c in self.capabilities()],
            },
            path=CognitionPath.S,
            context=f"Sub-module {self.name} registering",
        )

    # ── Lifecycle ──

    async def start(self) -> None:
        """Start the submodule and register with the parent via bus."""
        await self._register_via_bus()
        self._logger.action(f"Sub-module {self.qualified_name} started")

    async def stop(self) -> None:
        self._logger.action(f"Sub-module {self.qualified_name} stopped")
