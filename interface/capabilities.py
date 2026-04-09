"""Capability system for submodules.

A Capability describes a named action a submodule can perform.
Other modules discover and invoke capabilities through a standardized
interface, similar to tool declarations in LLM systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Capability:
    """A named action that a submodule can perform.

    Each capability maps to an ``_invoke_{name}`` method on the owning
    SubModule. The input/output schemas are documentation for callers.
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for announce() and capability discovery."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }
