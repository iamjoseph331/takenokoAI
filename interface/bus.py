"""Intermodule message bus for TakenokoAI.

All communication between families flows through the MessageBus.
Messages carry structured metadata and follow cognition paths.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Coroutine

from pydantic import BaseModel, field_validator

from interface.logging import ModuleLogger


class FamilyPrefix(StrEnum):
    """Two-letter prefix identifying each family."""

    Re = "Re"
    Pr = "Pr"
    Ev = "Ev"
    Me = "Me"
    Mo = "Mo"


class CognitionPath(StrEnum):
    """Named paths representing common cognitive message flows."""

    P = "P"  # Deliberate: Ev -> Pr -> Ev -> Mo | Me
    R = "R"  # Reflex: Re -> Mo
    E = "E"  # Appraisal: Re -> Ev
    U = "U"  # Uptake: Re -> Pr
    D = "D"  # Dispatch: Pr -> Re | Ev | Mo | Me


# SUGGESTION (Configurable routes):
# Move VALID_PATH_ROUTES to default.yaml so new cognitive paths can be added
# without code changes. Format:
#   paths:
#     P: [[Ev, Pr], [Pr, Ev], [Ev, Mo], [Ev, Me]]
#     R: [[Re, Mo]]
#     ...
# Load in MessageBus.__init__() and validate at boot. Keep the current dict
# as a fallback default if no YAML config is provided.

# Valid (sender, receiver) pairs for each cognition path
VALID_PATH_ROUTES: dict[CognitionPath, list[tuple[FamilyPrefix, FamilyPrefix]]] = {
    CognitionPath.P: [
        (FamilyPrefix.Ev, FamilyPrefix.Pr),
        (FamilyPrefix.Pr, FamilyPrefix.Ev),
        (FamilyPrefix.Ev, FamilyPrefix.Mo),
        (FamilyPrefix.Ev, FamilyPrefix.Me),
    ],
    CognitionPath.R: [
        (FamilyPrefix.Re, FamilyPrefix.Mo),
    ],
    CognitionPath.E: [
        (FamilyPrefix.Re, FamilyPrefix.Ev),
    ],
    CognitionPath.U: [
        (FamilyPrefix.Re, FamilyPrefix.Pr),
    ],
    CognitionPath.D: [
        (FamilyPrefix.Pr, FamilyPrefix.Re),
        (FamilyPrefix.Pr, FamilyPrefix.Ev),
        (FamilyPrefix.Pr, FamilyPrefix.Mo),
        (FamilyPrefix.Pr, FamilyPrefix.Me),
    ],
}

# Regex for message IDs: <2-letter prefix><8-digit counter><path letter>
# Lowercase prefix indicates an ack message (e.g. "pr00000012P" acks "Pr00000012P")
MESSAGE_ID_PATTERN = re.compile(
    r"^(Re|Pr|Ev|Me|Mo|re|pr|ev|me|mo)\d{8}[PREUD]$"
)

DEFAULT_QUEUE_MAXSIZE = 5


@dataclass(frozen=True)
class QueueFullSignal:
    """Returned by MessageBus.send() when the receiver's queue is full."""

    receiver: str
    queue_size: int
    message_id: str


class BusMessage(BaseModel):
    """A message transmitted between families on the bus."""

    message_id: str
    parent_message_id: str | None = None
    trace_id: str = ""
    timecode: float
    context: str = ""
    body: Any = None
    sender: FamilyPrefix
    receiver: FamilyPrefix
    resources: dict[str, Any] | None = None
    is_ack: bool = False

    @field_validator("message_id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        if not MESSAGE_ID_PATTERN.match(v):
            raise ValueError(
                f"Invalid message_id format: {v!r}. "
                f"Expected <prefix><8-digit counter><path letter>."
            )
        return v


class MessageBus:
    """Central message bus for intermodule communication.

    Each registered module gets a bounded asyncio.Queue for incoming messages.
    Queue sizes are configurable per-family to provide backpressure.
    The bus validates routes against cognition path rules before delivery.
    """

    def __init__(
        self,
        logger: ModuleLogger,
        queue_limits: dict[str, int] | None = None,
    ) -> None:
        self._logger = logger
        self._queue_limits = queue_limits or {}
        self._queues: dict[str, asyncio.Queue[BusMessage]] = {}
        self._subscribers: dict[
            str, Callable[[BusMessage], Coroutine[Any, Any, None]]
        ] = {}

    def _resolve_maxsize(self, module_name: str) -> int:
        """Resolve queue maxsize for a module.

        Checks in order: exact module name, family prefix, then default.
        """
        if module_name in self._queue_limits:
            return self._queue_limits[module_name]
        prefix = module_name.split(".")[0] if "." in module_name else module_name
        return self._queue_limits.get(prefix, DEFAULT_QUEUE_MAXSIZE)

    def register(self, module_name: str) -> asyncio.Queue[BusMessage]:
        """Register a module and return its bounded message queue."""
        if module_name in self._queues:
            raise ValueError(f"Module {module_name!r} is already registered on the bus")
        maxsize = self._resolve_maxsize(module_name)
        queue: asyncio.Queue[BusMessage] = asyncio.Queue(maxsize=maxsize)
        self._queues[module_name] = queue
        self._logger.action(
            f"Registered module on bus: {module_name} (queue maxsize={maxsize})"
        )
        return queue

    def unregister(self, module_name: str) -> None:
        """Remove a module from the bus."""
        self._queues.pop(module_name, None)
        self._subscribers.pop(module_name, None)
        self._logger.action(f"Unregistered module from bus: {module_name}")

    async def send(self, message: BusMessage) -> QueueFullSignal | None:
        """Validate and route a message to its receiver's queue.

        Returns None on success, or a QueueFullSignal if the receiver's
        queue is at capacity (backpressure signal to the sender).
        """
        receiver_name = self._resolve_receiver(message.receiver.value)

        self._logger.bus_message(
            f"{message.sender} -> {message.receiver} [{message.message_id}]"
            + (f" trace={message.trace_id}" if message.trace_id else ""),
            data={"body_preview": str(message.body)[:200]},
        )

        try:
            self._queues[receiver_name].put_nowait(message)
        except asyncio.QueueFull:
            queue_size = self._queues[receiver_name].qsize()
            self._logger.action(
                f"BACKPRESSURE: Queue full for {receiver_name} "
                f"(size={queue_size}), message {message.message_id} rejected"
            )
            return QueueFullSignal(
                receiver=receiver_name,
                queue_size=queue_size,
                message_id=message.message_id,
            )

        # Fire subscriber callback if one exists
        if receiver_name in self._subscribers:
            await self._subscribers[receiver_name](message)

        return None

    async def receive(
        self, module_name: str, *, timeout: float | None = None
    ) -> BusMessage:
        """Wait for and return the next message for a module."""
        if module_name not in self._queues:
            raise ValueError(f"Module {module_name!r} is not registered on the bus")
        if timeout is not None:
            return await asyncio.wait_for(
                self._queues[module_name].get(), timeout=timeout
            )
        return await self._queues[module_name].get()

    def subscribe(
        self,
        module_name: str,
        callback: Callable[[BusMessage], Coroutine[Any, Any, None]],
    ) -> None:
        """Set an async callback that fires on every message delivered to module_name."""
        self._subscribers[module_name] = callback

    def _resolve_receiver(self, receiver_name: str) -> str:
        """Find the actual queue key for a receiver (plain prefix or qualified name)."""
        if receiver_name in self._queues:
            return receiver_name
        qualified = f"{receiver_name}.main"
        if qualified in self._queues:
            return qualified
        raise ValueError(
            f"Receiver {receiver_name!r} is not registered on the bus"
        )

    @staticmethod
    def make_message_id(
        prefix: FamilyPrefix, counter: int, path: CognitionPath
    ) -> str:
        """Build a message ID string: <prefix><8-digit counter><path letter>."""
        return f"{prefix.value}{counter:08d}{path.value}"

    @staticmethod
    def make_ack_id(original_id: str) -> str:
        """Build an ack message ID by lowercasing the 2-letter prefix.

        e.g. "Pr00000012P" -> "pr00000012P"
        """
        return original_id[:2].lower() + original_id[2:]

    @staticmethod
    def validate_route(
        sender: FamilyPrefix, receiver: FamilyPrefix, path: CognitionPath
    ) -> bool:
        """Check whether (sender, receiver) is valid for the given cognition path."""
        valid = VALID_PATH_ROUTES.get(path, [])
        return (sender, receiver) in valid

    @staticmethod
    def now() -> float:
        """Return a monotonic timecode for message timestamps."""
        return time.monotonic()
