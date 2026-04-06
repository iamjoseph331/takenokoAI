"""Capability declaration system for submodules.

Each submodule declares its capabilities — named actions it can perform,
with typed input/output schemas. This enables:
  - Discovery: other families can query what capabilities are available
  - Invocation: standardized way to call any submodule capability
  - Composability: attach/detach capabilities at runtime like tools

Design mirrors how tools work in Claude Code: each tool has a name,
description, and schema. Here, each Capability is a tool a submodule
provides to the agent.

Usage:
    class MySubmodule(SubModule):
        def capabilities(self) -> list[Capability]:
            return [
                Capability(
                    name="transcribe",
                    description="Convert audio to text",
                    input_schema={"audio_b64": "base64-encoded audio"},
                    output_schema={"text": "transcribed text"},
                ),
            ]

        async def _invoke_transcribe(self, params: dict) -> dict:
            audio = base64.b64decode(params["audio_b64"])
            text = await self._backend.transcribe(audio)
            return {"status": "ok", "text": text}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Capability:
    """A single capability provided by a submodule.

    Attributes:
        name: Short identifier, also used as the invoke key (e.g. "transcribe").
              The submodule must implement `_invoke_{name}(params)`.
        description: Human-readable description of what this capability does.
        input_schema: Dict describing expected input parameters.
        output_schema: Dict describing the output format.
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for announce() and discovery."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }
