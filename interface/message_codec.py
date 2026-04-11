"""MessageCodec — parses LLM output into structured bus message fields.

LLM output format (JSON):
{
    "body": "...",
    "path": "P",
    "receiver": "Ev",
    "summary": "<Re> got new board, asking <Ev> to evaluate"
}

The codec validates the path and receiver, and falls back to sensible
defaults when the LLM produces invalid output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from interface.bus import BusMessage, CognitionPath, FamilyPrefix
from interface.logging import ModuleLogger


# Fallback routes: given (incoming_path, receiver_family), infer (response_path, response_target)
_FALLBACK_ROUTES: dict[
    tuple[CognitionPath, FamilyPrefix], tuple[CognitionPath, FamilyPrefix]
] = {
    (CognitionPath.U, FamilyPrefix.Pr): (CognitionPath.D, FamilyPrefix.Mo),
    (CognitionPath.P, FamilyPrefix.Pr): (CognitionPath.P, FamilyPrefix.Ev),
    (CognitionPath.P, FamilyPrefix.Ev): (CognitionPath.P, FamilyPrefix.Pr),
    (CognitionPath.D, FamilyPrefix.Mo): (CognitionPath.D, FamilyPrefix.Mo),
    (CognitionPath.E, FamilyPrefix.Ev): (CognitionPath.P, FamilyPrefix.Pr),
    (CognitionPath.R, FamilyPrefix.Mo): (CognitionPath.R, FamilyPrefix.Mo),
}


def infer_fallback_route(
    message: BusMessage, self_prefix: FamilyPrefix
) -> tuple[CognitionPath, FamilyPrefix]:
    """Infer response route when LLM doesn't specify one.

    Looks up the incoming message's path + receiver in _FALLBACK_ROUTES.
    Falls back to S-path (self-directed) if no mapping exists.
    """
    # Extract path letter from message_id (last char)
    path_letter = message.message_id[-1]
    try:
        incoming_path = CognitionPath(path_letter)
    except ValueError:
        return (CognitionPath.S, self_prefix)

    key = (incoming_path, self_prefix)
    if key in _FALLBACK_ROUTES:
        return _FALLBACK_ROUTES[key]

    # Default: S-path to self
    return (CognitionPath.S, self_prefix)


@dataclass
class ParsedLLMOutput:
    """Structured result of parsing an LLM response."""

    body: str
    path: CognitionPath | None
    receiver: FamilyPrefix | None
    summary: str
    raw: str
    parse_error: str | None = None


# Prompt instructions that tell the LLM how to format its output
FORMAT_INSTRUCTIONS = """You MUST respond in valid JSON. Your response contains one or more messages to send.

Format — array of messages:
{
    "messages": [
        {
            "body": "<your response/reasoning>",
            "path": "<one of: P, R, E, U, D, S, N>",
            "receiver": "<one of: Re, Pr, Ev, Me, Mo>",
            "summary": "<one-line broadcast summary>"
        }
    ]
}

Rules:
- "messages" is an array of one or more messages to send.
- Each message has: body, path, receiver, summary.
- "body" contains your actual response content.
- "path" is the cognition path for the message.
- "receiver" is the target family.
- "summary" is a short broadcast that all families will see.
- You may send multiple messages at once (e.g., send reasoning to Pr AND a filler response to Mo).
- You are encouraged to send internal thoughts whenyou have spare time, use a single message with path "S" and receiver set to your own family prefix."""


def _extract_json(raw: str) -> dict | None:
    """Try to extract a JSON object from raw LLM output."""
    cleaned = raw.strip()

    # Try to extract JSON from markdown code blocks
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        start = 1
        end = len(lines)
        for i in range(1, len(lines)):
            if lines[i].strip() == "```":
                end = i
                break
        cleaned = "\n".join(lines[start:end])

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Last resort: find outermost braces
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _parse_single_message(
    data: dict,
    raw: str,
    logger: ModuleLogger,
) -> ParsedLLMOutput:
    """Parse a single message dict into ParsedLLMOutput."""
    body = data.get("body", raw)
    summary = data.get("summary", "")

    path: CognitionPath | None = None
    path_str = data.get("path", "")
    if path_str:
        try:
            path = CognitionPath(path_str)
        except ValueError:
            logger.action(
                f"Invalid path in LLM output: {path_str!r}",
                data={"valid": [p.value for p in CognitionPath]},
            )

    receiver: FamilyPrefix | None = None
    receiver_str = data.get("receiver", "")
    if receiver_str:
        try:
            receiver = FamilyPrefix(receiver_str)
        except ValueError:
            logger.action(
                f"Invalid receiver in LLM output: {receiver_str!r}",
                data={"valid": [f.value for f in FamilyPrefix]},
            )

    return ParsedLLMOutput(
        body=body,
        path=path,
        receiver=receiver,
        summary=summary,
        raw=raw,
    )


def parse_llm_outputs(
    raw: str,
    sender: FamilyPrefix,
    logger: ModuleLogger,
) -> list[ParsedLLMOutput]:
    """Parse an LLM response into a list of structured message fields.

    Supports both the new array format ({"messages": [...]}) and the
    legacy single-object format ({"body": ...}). Falls back to a
    single ParsedLLMOutput with the raw text if JSON parsing fails.
    """
    raw = raw.strip()
    data = _extract_json(raw)

    if data is None:
        logger.action(
            "No JSON found in LLM output",
            data={"raw_preview": raw[:200]},
        )
        return [ParsedLLMOutput(
            body=raw,
            path=None,
            receiver=None,
            summary="",
            raw=raw,
            parse_error="No JSON object found",
        )]

    # New array format: {"messages": [...]}
    if "messages" in data and isinstance(data["messages"], list):
        results = []
        for item in data["messages"]:
            if isinstance(item, dict):
                results.append(_parse_single_message(item, raw, logger))
        if results:
            return results
        # Empty messages array — fall through to single-object parse

    # Legacy single-object format: {"body": ..., "path": ..., ...}
    if "body" in data:
        return [_parse_single_message(data, raw, logger)]

    # JSON parsed but no recognized structure
    logger.action(
        "Failed to parse LLM output as JSON",
        data={"raw_preview": raw[:200]},
    )
    return [ParsedLLMOutput(
        body=raw,
        path=None,
        receiver=None,
        summary="",
        raw=raw,
        parse_error="Not valid JSON",
    )]


def parse_llm_output(
    raw: str,
    sender: FamilyPrefix,
    logger: ModuleLogger,
) -> ParsedLLMOutput:
    """Backward-compatible convenience: returns the first parsed output."""
    return parse_llm_outputs(raw, sender, logger)[0]
