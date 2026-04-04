"""Me.rules — game rule memory submodule (placeholder).

Stores, retrieves, and reasons about game rules that the agent learns
through conversation with the user. Rules are built up incrementally
as the user explains the game, and refined through play experience.

This is a placeholder — see TODO.md for the full implementation plan.

Planned capabilities:
  - Store rules as structured entries (rule text, source, confidence)
  - Retrieve relevant rules given a game state description
  - Update/refine rules based on play experience and corrections
  - Distinguish between confirmed rules and uncertain interpretations
  - Support multiple games simultaneously (keyed by game name)

Usage (future):
    rules_sub = RulesSubmodule(parent=me_module)
    await rules_sub.start()
    await rules_sub.add_rule("tictactoe", "Players alternate turns placing X and O")
    rules = await rules_sub.get_rules("tictactoe")
    relevant = await rules_sub.query_rules("tictactoe", "Can I place on an occupied cell?")
"""

from __future__ import annotations

from typing import Any, Optional

from interface.bus import BusMessage
from interface.modules import MainModule, SubModule


class RulesSubmodule(SubModule):
    """Game rule memory submodule for the Memorization family.

    Stores game rules learned through user conversation. Other families
    (especially Pr and Ev) query this module to understand what moves
    are legal and what the game objectives are.

    NOTE: This is a placeholder. The full implementation is tracked in TODO.md.
    """

    def __init__(self, parent: MainModule) -> None:
        super().__init__(
            parent=parent,
            name="rules",
            description=(
                "Game rule memory: stores and retrieves game rules learned "
                "through conversation, enabling the agent to play new games "
                "by understanding their rules"
            ),
            llm_config=parent._llm.config,
        )
        # Keyed by game name → list of rule entries
        self._rules: dict[str, list[dict[str, Any]]] = {}

    async def add_rule(
        self, game: str, rule_text: str, *, source: str = "user", confidence: float = 1.0
    ) -> str:
        """Store a game rule. Returns a rule ID."""
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
        return rule_id

    async def get_rules(self, game: str) -> list[dict[str, Any]]:
        """Get all stored rules for a game."""
        return list(self._rules.get(game, []))

    async def query_rules(self, game: str, question: str) -> list[dict[str, Any]]:
        """Find rules relevant to a question (placeholder: returns all rules).

        TODO: Use LLM or semantic search to find relevant rules.
        """
        return await self.get_rules(game)

    async def clear_rules(self, game: str) -> int:
        """Remove all rules for a game. Returns count of removed rules."""
        count = len(self._rules.pop(game, []))
        self._logger.action(f"Cleared {count} rules for {game}")
        return count

    async def handle_message(self, message: BusMessage) -> Optional[BusMessage]:
        """Handle rule-related messages.

        Expected body formats:
          - {"action": "add_rule", "game": "...", "rule": "..."}
          - {"action": "get_rules", "game": "..."}
          - {"action": "query_rules", "game": "...", "question": "..."}
          - {"action": "clear_rules", "game": "..."}
        """
        body = message.body or {}
        if not isinstance(body, dict):
            return None

        action = body.get("action", "")
        game = body.get("game", "unknown")

        if action == "add_rule":
            rule_text = body.get("rule", "")
            source = body.get("source", str(message.sender.value))
            await self.add_rule(game, rule_text, source=source)

        elif action == "get_rules":
            rules = await self.get_rules(game)
            self._logger.action(f"Returned {len(rules)} rules for {game}")

        elif action == "query_rules":
            question = body.get("question", "")
            rules = await self.query_rules(game, question)
            self._logger.action(f"Query '{question[:50]}' matched {len(rules)} rules")

        elif action == "clear_rules":
            await self.clear_rules(game)

        return None

    async def start(self) -> None:
        await super().start()
        self._logger.action("Game rule memory ready (placeholder)")

    async def stop(self) -> None:
        await super().stop()
