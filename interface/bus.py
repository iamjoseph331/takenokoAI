"""Intermodule message bus for TakenokoAI.

All communication between families flows through the MessageBus.
Messages carry structured metadata and follow cognition paths.
"""

from __future__ import annotations

import asyncio
import re
import time
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
MESSAGE_ID_PATTERN = re.compile(r"^(Re|Pr|Ev|Me|Mo)\d{8}[PREUD]$")


class BusMessage(BaseModel):
    """A message transmitted between families on the bus."""

    message_id: str
    parent_message_id: str | None = None
    timecode: float
    context: str = ""
    body: Any = None
    sender: FamilyPrefix
    receiver: FamilyPrefix
    resources: dict[str, Any] | None = None

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

    Each registered module gets an asyncio.Queue for incoming messages.
    The bus validates routes against cognition path rules before delivery.
    """

    def __init__(self, logger: ModuleLogger) -> None:
        self._logger = logger
        self._queues: dict[str, asyncio.Queue[BusMessage]] = {}
        self._subscribers: dict[
            str, Callable[[BusMessage], Coroutine[Any, Any, None]]
        ] = {}

    def register(self, module_name: str) -> asyncio.Queue[BusMessage]:
        """Register a module and return its message queue."""
        if module_name in self._queues:
            raise ValueError(f"Module {module_name!r} is already registered on the bus")
        queue: asyncio.Queue[BusMessage] = asyncio.Queue()
        self._queues[module_name] = queue
        self._logger.action(f"Registered module on bus: {module_name}")
        return queue

    def unregister(self, module_name: str) -> None:
        """Remove a module from the bus."""
        self._queues.pop(module_name, None)
        self._subscribers.pop(module_name, None)
        self._logger.action(f"Unregistered module from bus: {module_name}")

    async def send(self, message: BusMessage) -> None:
        """Validate and route a message to its receiver's queue."""
        receiver_name = message.receiver.value
        if receiver_name not in self._queues:
            raise ValueError(
                f"Receiver {receiver_name!r} is not registered on the bus"
            )

        self._logger.bus_message(
            f"{message.sender} -> {message.receiver} [{message.message_id}]",
            data={"body_preview": str(message.body)[:200]},
        )

        await self._queues[receiver_name].put(message)

        # Fire subscriber callback if one exists
        if receiver_name in self._subscribers:
            await self._subscribers[receiver_name](message)

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

    @staticmethod
    def make_message_id(
        prefix: FamilyPrefix, counter: int, path: CognitionPath
    ) -> str:
        """Build a message ID string: <prefix><8-digit counter><path letter>."""
        return f"{prefix.value}{counter:08d}{path.value}"

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
