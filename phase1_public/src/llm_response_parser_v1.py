"""Deterministic response-channel selection and JSON extraction for v4-flash.

Selection rule:
    final response = reasoning_content when it contains parseable JSON;
    otherwise final response = content.

The parser is deliberately conservative for prose-wrapped output: extracted
objects are accepted only when they look like the expected review root, so a
small legal-evidence object embedded in free-form reasoning is not mistaken
for the model's final response. A strict JSON object with the wrong schema is
still selected according to the requested channel-priority rule, then left
for the post-LLM schema gate to block.
"""

from __future__ import annotations

import json
import re
from typing import Any


EXPECTED_ROOT_KEYS = {
    "findings",
    "review_table",
    "table_markdown",
    "output_format",
    "overall_review_status",
}


def _try_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None


def _balanced_end(text: str, start: int) -> int | None:
    opening = text[start]
    if opening not in "[{":
        return None
    closing = "]" if opening == "[" else "}"
    stack = [closing]
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


def parse_json_candidate(text: str | None) -> dict[str, Any]:
    if not isinstance(text, str):
        text = ""
    normalized = text.lstrip("\ufeff").strip()
    base = {
        "status": "empty" if not normalized else "invalid",
        "method": "empty" if not normalized else "none",
        "parsed": None,
        "text_length": len(text),
        "candidate_length": 0,
        "normalization": "bom_and_outer_whitespace_removed" if normalized else "none",
        "root_type": None,
        "schema_score": 0,
        "schema_compatible": False,
        "error": "empty" if not normalized else "no_parseable_json",
    }
    if not normalized:
        return base

    parsed = _try_json(normalized)
    if parsed is not None:
        schema_score = _schema_score(parsed)
        return {
            **base,
            "status": "parsed",
            "method": "strict_json",
            "parsed": parsed,
            "candidate_length": len(normalized),
            "normalization": "bom_and_outer_whitespace_removed",
            "root_type": type(parsed).__name__,
            "schema_score": schema_score,
            "schema_compatible": schema_score > 0,
            "error": None,
        }

    fence_match = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", normalized, flags=re.IGNORECASE)
    if fence_match:
        fenced = fence_match.group(1).strip()
        parsed = _try_json(fenced)
        if parsed is not None:
            schema_score = _schema_score(parsed)
            return {
                **base,
                "status": "parsed",
                "method": "markdown_fence",
                "parsed": parsed,
                "candidate_length": len(fenced),
                "normalization": "bom_outer_whitespace_and_markdown_fence_removed",
                "root_type": type(parsed).__name__,
                "schema_score": schema_score,
                "schema_compatible": schema_score > 0,
                "error": None,
            }

    candidates: list[tuple[int, int, Any]] = []
    for start, char in enumerate(normalized):
        if char not in "[{":
            continue
        end = _balanced_end(normalized, start)
        if end is None:
            continue
        candidate_text = normalized[start:end]
        candidate = _try_json(candidate_text)
        if candidate is None:
            continue
        schema_score = _schema_score(candidate)
        candidates.append((schema_score, len(candidate_text), candidate))

    if candidates:
        schema_score, candidate_length, candidate = max(candidates, key=lambda item: (item[0], item[1]))
        if schema_score > 0:
            return {
                **base,
                "status": "parsed",
                "method": "balanced_json_extraction",
                "parsed": candidate,
                "candidate_length": candidate_length,
                "normalization": "bom_outer_whitespace_and_surrounding_prose_removed",
                "root_type": type(candidate).__name__,
                "schema_score": schema_score,
                "schema_compatible": True,
                "error": None,
            }

    return base


def _schema_score(parsed: Any) -> int:
    if not isinstance(parsed, dict):
        return 0
    return len(set(parsed).intersection(EXPECTED_ROOT_KEYS))


def _is_response_json(parsed: Any, diagnostics: dict[str, Any]) -> bool:
    """Apply channel priority to parseable JSON; schema validity is gate-owned."""

    if parsed is None:
        return False
    if diagnostics.get("method") in {"strict_json", "markdown_fence"}:
        return True
    return diagnostics.get("schema_compatible", False)


def channel_diagnostic_snapshot(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """Return auditable channel metadata without duplicating the parsed payload."""

    return {key: value for key, value in diagnostics.items() if key != "parsed"}


def select_final_response(message: dict[str, Any] | None) -> dict[str, Any]:
    message = message if isinstance(message, dict) else {}
    reasoning_text = message.get("reasoning_content") or ""
    content_text = message.get("content") or ""
    reasoning = parse_json_candidate(reasoning_text)
    content = parse_json_candidate(content_text)
    reasoning["channel_present"] = "reasoning_content" in message and message.get("reasoning_content") is not None
    reasoning["channel_nonempty"] = bool(reasoning_text.strip()) if isinstance(reasoning_text, str) else bool(reasoning_text)
    content["channel_present"] = "content" in message and message.get("content") is not None
    content["channel_nonempty"] = bool(content_text.strip()) if isinstance(content_text, str) else bool(content_text)

    if _is_response_json(reasoning["parsed"], reasoning):
        return {
            "selected_channel": "reasoning_content",
            "selection_rule": "reasoning_content_preferred_when_parseable",
            "selected_text": reasoning_text,
            "parsed": reasoning["parsed"],
            "selected_parse_method": reasoning["method"],
            "reasoning_content": reasoning,
            "content": content,
        }
    if _is_response_json(content["parsed"], content):
        return {
            "selected_channel": "content",
            "selection_rule": "content_fallback_when_reasoning_content_unparseable",
            "selected_text": content_text,
            "parsed": content["parsed"],
            "selected_parse_method": content["method"],
            "reasoning_content": reasoning,
            "content": content,
        }
    if content_text.strip():
        return {
            "selected_channel": "content",
            "selection_rule": "content_fallback_when_reasoning_content_unparseable_but_content_not_parseable",
            "selected_text": content_text,
            "parsed": None,
            "selected_parse_method": content["method"],
            "reasoning_content": reasoning,
            "content": content,
        }
    return {
        "selected_channel": "none",
        "selection_rule": "content_fallback_empty",
        "selected_text": "",
        "parsed": None,
        "selected_parse_method": "empty",
        "reasoning_content": reasoning,
        "content": content,
    }
