"""Schema-specific response-channel parsing for hierarchy triage calls.

The final-review parser intentionally prefers objects that resemble the review
root.  Hierarchy triage has a different, much smaller contract, so prose-wrapped
JSON must be validated against ``level_state`` rather than final-review keys.
"""

from __future__ import annotations

import json
import re
from typing import Any


VALID_LEVEL_STATES = {
    "violation_or_inconsistency_detected",
    "no_usable_violation_found",
    "relevant_but_inconclusive",
}


def _balanced_end(text: str, start: int) -> int | None:
    if text[start] not in "[{":
        return None
    stack = ["]" if text[start] == "[" else "}"]
    in_string = False
    escaped = False
    for index in range(start + 1, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            stack.append("]" if char == "[" else "}")
        elif char in "]}":
            if not stack or char != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return index + 1
    return None


def _valid_triage_root(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("level_state") in VALID_LEVEL_STATES
        and isinstance(value.get("selected_chunk_ids", []), list)
        and isinstance(value.get("missing_elements", []), list)
    )


def parse_triage_candidate(text: str | None) -> dict[str, Any]:
    raw = text if isinstance(text, str) else ""
    normalized = raw.lstrip("\ufeff").strip()
    base = {
        "status": "empty" if not normalized else "invalid",
        "method": "empty" if not normalized else "none",
        "parsed": None,
        "text_length": len(raw),
        "candidate_length": 0,
        "schema_compatible": False,
        "error": "empty" if not normalized else "no_valid_triage_json",
    }
    if not normalized:
        return base

    attempts: list[tuple[str, str]] = [("strict_json", normalized)]
    fence = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", normalized, flags=re.IGNORECASE)
    if fence:
        attempts.append(("markdown_fence", fence.group(1).strip()))
    for method, candidate_text in attempts:
        try:
            parsed = json.loads(candidate_text)
        except json.JSONDecodeError:
            continue
        if _valid_triage_root(parsed):
            return {
                **base,
                "status": "parsed",
                "method": method,
                "parsed": parsed,
                "candidate_length": len(candidate_text),
                "schema_compatible": True,
                "error": None,
            }

    candidates: list[tuple[int, dict[str, Any]]] = []
    for start, char in enumerate(normalized):
        if char != "{":
            continue
        end = _balanced_end(normalized, start)
        if end is None:
            continue
        candidate_text = normalized[start:end]
        try:
            parsed = json.loads(candidate_text)
        except json.JSONDecodeError:
            continue
        if _valid_triage_root(parsed):
            candidates.append((len(candidate_text), parsed))
    if candidates:
        candidate_length, parsed = max(candidates, key=lambda item: item[0])
        return {
            **base,
            "status": "parsed",
            "method": "balanced_triage_json_extraction",
            "parsed": parsed,
            "candidate_length": candidate_length,
            "schema_compatible": True,
            "error": None,
        }
    return base


def diagnostic_snapshot(parsed: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in parsed.items() if key != "parsed"}


def select_triage_response(message: dict[str, Any] | None) -> dict[str, Any]:
    message = message if isinstance(message, dict) else {}
    reasoning_text = message.get("reasoning_content") or ""
    content_text = message.get("content") or ""
    reasoning = parse_triage_candidate(reasoning_text)
    content = parse_triage_candidate(content_text)
    for parsed, key, value in (
        (reasoning, "reasoning_content", reasoning_text),
        (content, "content", content_text),
    ):
        parsed["channel_present"] = key in message and message.get(key) is not None
        parsed["channel_nonempty"] = bool(value.strip()) if isinstance(value, str) else bool(value)

    if reasoning.get("parsed") is not None:
        selected_channel = "reasoning_content"
        selected = reasoning
        selected_text = reasoning_text
        rule = "reasoning_content_preferred_when_valid_triage_json"
    elif content.get("parsed") is not None:
        selected_channel = "content"
        selected = content
        selected_text = content_text
        rule = "content_fallback_when_reasoning_has_no_valid_triage_json"
    elif content_text.strip():
        selected_channel = "content"
        selected = content
        selected_text = content_text
        rule = "content_fallback_unparseable"
    else:
        selected_channel = "none"
        selected = {"method": "empty", "parsed": None}
        selected_text = ""
        rule = "both_channels_without_valid_triage_json"

    return {
        "selected_channel": selected_channel,
        "selection_rule": rule,
        "selected_text": selected_text,
        "parsed": selected.get("parsed"),
        "selected_parse_method": selected.get("method"),
        "reasoning_content": reasoning,
        "content": content,
    }
