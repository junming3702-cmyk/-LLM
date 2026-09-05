"""Deterministic fixtures for the hierarchy-triage response parser."""

from __future__ import annotations

from triage_response_parser_v1 import parse_triage_candidate, select_triage_response


VALID = '{"level_state":"no_usable_violation_found","selected_chunk_ids":[],"reason":"ok","missing_elements":[],"confidence":"medium"}'


def main() -> int:
    strict = parse_triage_candidate(VALID)
    assert strict["method"] == "strict_json" and strict["schema_compatible"]

    wrapped = parse_triage_candidate("analysis before\n" + VALID + "\nanalysis after")
    assert wrapped["method"] == "balanced_triage_json_extraction"

    selected = select_triage_response(
        {
            "reasoning_content": "not valid triage JSON",
            "content": f"```json\n{VALID}\n```",
        }
    )
    assert selected["selected_channel"] == "content"
    assert selected["parsed"]["level_state"] == "no_usable_violation_found"

    rejected = parse_triage_candidate('{"findings":[]}')
    assert rejected["parsed"] is None
    print("triage_response_parser_v1 fixtures: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
