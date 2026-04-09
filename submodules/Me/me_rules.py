"""Me.rules — game rule memory submodule.

Stores, retrieves, and reasons about game rules that the agent learns
through conversation with the user. Rules are built up incrementally
as the user explains the game, and refined through play experience.

Capabilities:
  - add_rule: Store a game rule
  - get_rules: Retrieve all rules for a game
  - query_rules: Find rules relevant to a question (placeholder)
  - clear_rules: Remove all rules for a game

Usage:
    rules_sub = RulesSubmodule(
        bus=bus, logger=logger, llm_config=llm_config,
        permissions=permissions,
    )
    await rules_sub.start()
    result = await rules_sub.invoke("add_rule", {"game": "tictactoe", "rule": "..."})
"""

from __future__ import annotations

from typing import Any

from interface.bus import (
    FamilyPrefix,
    MessageBus,
    QueueFullPolicy,
)
from interface.capabilities import Capability
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.modules import SubModule
from interface.permissions import PermissionManager


class RulesSubmodule(SubModule):
    """Game rule memory submodule for the Memorization family.

    Stores game rules learned through user conversation. Other families
    (especially Pr and Ev) query this module to understand what moves
    are legal and what the game objectives are.
    """

    def __init__(
        self,
        *,
        family_prefix: FamilyPrefix = FamilyPrefix.Me,
        bus: MessageBus,
        logger: ModuleLogger,
        llm_config: LLMConfig,
        permissions: PermissionManager,
        policy: QueueFullPolicy = QueueFullPolicy.WAIT,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            family_prefix=family_prefix,
            name="rules",
            description=(
                "Game rule memory: stores and retrieves game rules learned "
                "through conversation, enabling the agent to play new games "
                "by understanding their rules"
            ),
            bus=bus,
            logger=logger,
            llm_config=llm_config,
            permissions=permissions,
            policy=policy,
            max_retries=max_retries,
        )
        self._rules: dict[str, list[dict[str, Any]]] = {}

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="add_rule",
                description="Store a game rule",
                input_schema={
                    "game": "game name",
                    "rule": "rule text",
                    "source": "(optional) who provided the rule",
                    "confidence": "(optional) confidence 0.0-1.0",
                },
                output_schema={"status": "ok | error", "rule_id": "assigned rule ID"},
            ),
            Capability(
                name="get_rules",
                description="Retrieve all rules for a game",
                input_schema={"game": "game name"},
                output_schema={"status": "ok", "rules": "list of rule entries"},
            ),
            Capability(
                name="query_rules",
                description="Find rules relevant to a question (placeholder: returns all)",
                input_schema={"game": "game name", "question": "query string"},
                output_schema={"status": "ok", "rules": "list of matching rules"},
            ),
            Capability(
                name="clear_rules",
                description="Remove all rules for a game",
                input_schema={"game": "game name"},
                output_schema={"status": "ok", "cleared": "number of rules removed"},
            ),
        ]

    async def _invoke_add_rule(self, params: dict[str, Any]) -> dict[str, Any]:
        game = params.get("game", "unknown")
        rule_text = params.get("rule", "")
        if not rule_text:
            return {"status": "error", "reason": "Missing rule text"}

        source = params.get("source", "user")
        confidence = float(params.get("confidence", 1.0))

        if game not in self._rules:
            self._rules[game] = []

        rule_id = f"rule-{game}-{len(self._rules[game])}"
        self._rules[game].append({
            "id": rule_id,
            "text": rule_text,
            "source": source,
            "confidence": confidence,
        })
        self._logger.action(f"Rule added: [{game}] {rule_text[:80]}")
        return {"status": "ok", "rule_id": rule_id}

    async def _invoke_get_rules(self, params: dict[str, Any]) -> dict[str, Any]:
        game = params.get("game", "unknown")
        rules = list(self._rules.get(game, []))
        return {"status": "ok", "rules": rules}

    async def _invoke_query_rules(self, params: dict[str, Any]) -> dict[str, Any]:
        game = params.get("game", "unknown")
        # Placeholder: returns all rules. TODO: semantic search.
        rules = list(self._rules.get(game, []))
        return {"status": "ok", "rules": rules}

    async def _invoke_clear_rules(self, params: dict[str, Any]) -> dict[str, Any]:
        game = params.get("game", "unknown")
        count = len(self._rules.pop(game, []))
        self._logger.action(f"Cleared {count} rules for {game}")
        return {"status": "ok", "cleared": count}

    async def start(self) -> None:
        await super().start()
        self._logger.action("Game rule memory ready")

    async def stop(self) -> None:
        await super().stop()
