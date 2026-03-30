"""Intermodule message bus for TakenokoAI.

All communication between families flows through the MessageBus.
Messages carry structured metadata and follow cognition paths.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
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
    S = "S"  # Self: sender == receiver (idle wake-up, reconsideration)


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
    CognitionPath.S: [
        (FamilyPrefix.Re, FamilyPrefix.Re),
        (FamilyPrefix.Pr, FamilyPrefix.Pr),
        (FamilyPrefix.Ev, FamilyPrefix.Ev),
        (FamilyPrefix.Me, FamilyPrefix.Me),
        (FamilyPrefix.Mo, FamilyPrefix.Mo),
    ],
}

MESSAGE_ID_PATTERN = re.compile(
    r"^(Re|Pr|Ev|Me|Mo|re|pr|ev|me|mo)\d{8}[PREUDS]$"
)

DEFAULT_QUEUE_MAXSIZE = 5
DEFAULT_BROADCAST_BUFFER_SIZE = 20


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
    is_broadcast: bool = False
    summary: str = ""

    @field_validator("message_id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        if not MESSAGE_ID_PATTERN.match(v):
            raise ValueError(
                f"Invalid message_id format: {v!r}. "
                f"Expected <prefix><8-digit counter><path letter>."
            )
        return v


@dataclass(frozen=True)
class Broadcast:
    """A summary broadcast stored in the bus's circular buffer."""

    summary: str
    sender: FamilyPrefix
    timecode: float
    trace_id: str = ""


class MessageBus:
    """Central message bus for intermodule communication.

    Each registered module gets a bounded asyncio.Queue for incoming messages.
    Queue sizes are configurable per-family to provide backpressure.
    The bus validates routes against cognition path rules before delivery.

    Also maintains a circular buffer of recent broadcasts for context injection.
    """

    def __init__(
        self,
        logger: ModuleLogger,
        queue_limits: dict[str, int] | None = None,
        broadcast_buffer_size: int = DEFAULT_BROADCAST_BUFFER_SIZE,
    ) -> None:
        self._logger = logger
        self._queue_limits = queue_limits or {}
        self._queues: dict[str, asyncio.Queue[BusMessage]] = {}
        self._subscribers: dict[
            str, Callable[[BusMessage], Coroutine[Any, Any, None]]
        ] = {}
        self.pause_event: asyncio.Event = asyncio.Event()
        self.pause_event.set()  # start running (not paused)
        self._broadcasts: deque[Broadcast] = deque(maxlen=broadcast_buffer_size)
        # Optional hook called synchronously in send() for visualization
        self.viz_hook: Callable[[BusMessage], None] | None = None

    def _resolve_maxsize(self, module_name: str) -> int:
        """Resolve queue maxsize for a module."""
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

    def add_broadcast(self, broadcast: Broadcast) -> None:
        """Add a broadcast to the circular buffer."""
        self._broadcasts.append(broadcast)
        self._logger.bus_message(
            f"BROADCAST [{broadcast.sender}]: {broadcast.summary[:100]}"
        )

    def get_recent_broadcasts(self, n: int = 5) -> list[Broadcast]:
        """Return the last N broadcasts (most recent last)."""
        items = list(self._broadcasts)
        return items[-n:] if len(items) > n else items

    async def send(self, message: BusMessage) -> QueueFullSignal | None:
        """Validate and route a message to its receiver's queue."""
        receiver_name = self._resolve_receiver(message.receiver.value)

        self._logger.bus_message(
            f"{message.sender} -> {message.receiver} [{message.message_id}]"
            + (f" trace={message.trace_id}" if message.trace_id else ""),
            data={"body_preview": str(message.body)[:200]},
        )

        # Record broadcast if summary is present
        if message.summary:
            self.add_broadcast(Broadcast(
                summary=message.summary,
                sender=message.sender,
                timecode=message.timecode,
                trace_id=message.trace_id,
            ))

        # Fire visualization hook (non-blocking, best-effort)
        if self.viz_hook is not None:
            try:
                self.viz_hook(message)
            except Exception:
                pass

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

        if receiver_name in self._subscribers:
            await self._subscribers[receiver_name](message)

        return None

    async def receive(
        self, module_name: str, *, timeout: float | None = None
    ) -> BusMessage:
        """Wait for and return the next message for a module."""
        if module_name not in self._queues:
            raise ValueError(f"Module {module_name!r} is not registered on the bus")
        await self.pause_event.wait()
        if timeout is not None:
            return await asyncio.wait_for(
                self._queues[module_name].get(), timeout=timeout
            )
        return await self._queues[module_name].get()

    def has_pending(self, module_name: str) -> bool:
        """Check if a module has pending messages (non-blocking)."""
        q = self._queues.get(module_name)
        return q is not None and not q.empty()

    def subscribe(
        self,
        module_name: str,
        callback: Callable[[BusMessage], Coroutine[Any, Any, None]],
    ) -> None:
        """Set an async callback that fires on every message delivered to module_name."""
        self._subscribers[module_name] = callback

    def _resolve_receiver(self, receiver_name: str) -> str:
        """Find the actual queue key for a receiver."""
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
        """Build an ack message ID by lowercasing the 2-letter prefix."""
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
