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
from typing import Any

from interface.bus import CognitionPath, FamilyPrefix
from interface.logging import ModuleLogger


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
FORMAT_INSTRUCTIONS = """You MUST respond in valid JSON with exactly these keys:
{
    "body": "<your response/reasoning>",
    "path": "<one of: P, R, E, U, D, S>",
    "receiver": "<one of: Re, Pr, Ev, Me, Mo>",
    "summary": "<one-line summary of what you are doing, e.g. '<Re> routing board state to <Ev> for evaluation'>"
}

Rules:
- "body" contains your actual response content.
- "path" is the cognition path for the message you want to send.
- "receiver" is the target family.
- "summary" is a short broadcast that all families will see.
- If you have nothing to send (just answering a question), set path to "S", receiver to your own family prefix, and put your answer in body."""


def parse_llm_output(
    raw: str,
    sender: FamilyPrefix,
    logger: ModuleLogger,
) -> ParsedLLMOutput:
    """Parse an LLM response string into structured message fields.

    Attempts JSON parsing first. If that fails, treats the entire
    response as the body with no routing (returns path=None, receiver=None).
    """
    raw = raw.strip()

    # Try to extract JSON from markdown code blocks
    cleaned = raw
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
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Last resort: try to find JSON object in the response
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                logger.action(
                    f"Failed to parse LLM output as JSON",
                    data={"raw_preview": raw[:200]},
                )
                return ParsedLLMOutput(
                    body=raw,
                    path=None,
                    receiver=None,
                    summary="",
                    raw=raw,
                    parse_error="Not valid JSON",
                )
        else:
            logger.action(
                f"No JSON found in LLM output",
                data={"raw_preview": raw[:200]},
            )
            return ParsedLLMOutput(
                body=raw,
                path=None,
                receiver=None,
                summary="",
                raw=raw,
                parse_error="No JSON object found",
            )

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
