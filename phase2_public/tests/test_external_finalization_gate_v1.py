#!/usr/bin/env python3
"""Deterministic tests for the pre-final external-completion gate."""

from external_fallback_v2 import external_finalization_readiness


def completed_record(mode: str, *, basis: str = "provider_execution") -> dict:
    record = {
        "mode": mode,
        "requested": True,
        "status": "completed_no_hit",
        "external_search_completed": True,
        "scope_completion_basis": basis,
        "scope_coverage_ok": True,
        "human_attested": False,
        "scope_attestation_id": "",
    }
    if basis == "human_attested_manual_discovery":
        record["human_attested"] = True
        record["scope_attestation_id"] = "ATT-20260905-001"
    return record


def test_not_triggered_is_ready() -> None:
    audit = {
        "enabled": True,
        "external_search_completed": False,
        "discovery": {"requested": False},
        "verification": {"requested": False},
    }
    result = external_finalization_readiness(audit)
    assert result["required"] is False
    assert result["ready_for_final_llm"] is True
    assert result["status"] == "not_triggered"


def test_manifest_pending_blocks_final_llm() -> None:
    audit = {
        "enabled": True,
        "external_search_completed": False,
        "discovery": {"requested": False},
        "verification": {
            "requested": True,
            "status": "pending_human_scope_attestation",
            "external_search_completed": False,
            "scope_completion_basis": "manifest_lookup",
            "scope_coverage_ok": False,
        },
    }
    result = external_finalization_readiness(audit)
    assert result["required"] is True
    assert result["ready_for_final_llm"] is False
    assert result["status"] == "waiting_for_external_retrieval"
    assert "aggregate_external_search_not_completed" in result["reasons"]


def test_provider_completed_scope_allows_final_llm() -> None:
    audit = {
        "enabled": True,
        "external_search_completed": True,
        "discovery": {"requested": False},
        "verification": completed_record("verification"),
    }
    result = external_finalization_readiness(audit)
    assert result["ready_for_final_llm"] is True
    assert result["status"] == "external_retrieval_completed"
    assert result["completed_modes"] == ["verification"]


def test_bound_human_attestation_allows_final_llm() -> None:
    audit = {
        "enabled": True,
        "external_search_completed": True,
        "discovery": completed_record(
            "discovery", basis="human_attested_manual_discovery"
        ),
        "verification": {"requested": False},
    }
    result = external_finalization_readiness(audit)
    assert result["ready_for_final_llm"] is True
    assert result["completed_modes"] == ["discovery"]


def test_root_completion_claim_cannot_hide_incomplete_mode() -> None:
    audit = {
        "enabled": True,
        "external_search_completed": True,
        "discovery": {"requested": False},
        "verification": {
            "requested": True,
            "status": "completed_no_hit",
            "external_search_completed": False,
            "scope_completion_basis": "provider_execution",
            "scope_coverage_ok": False,
        },
    }
    result = external_finalization_readiness(audit)
    assert result["ready_for_final_llm"] is False
    assert "verification_external_search_completed_not_true" in result["reasons"]
    assert "verification_provider_scope_coverage_incomplete" in result["reasons"]


def test_human_attestation_requires_identifier() -> None:
    record = completed_record("discovery", basis="human_attested_manual_discovery")
    record["scope_attestation_id"] = ""
    audit = {
        "enabled": True,
        "external_search_completed": True,
        "discovery": record,
        "verification": {"requested": False},
    }
    result = external_finalization_readiness(audit)
    assert result["ready_for_final_llm"] is False
    assert "discovery_human_scope_attestation_incomplete" in result["reasons"]


if __name__ == "__main__":
    tests = [
        test_not_triggered_is_ready,
        test_manifest_pending_blocks_final_llm,
        test_provider_completed_scope_allows_final_llm,
        test_bound_human_attestation_allows_final_llm,
        test_root_completion_claim_cannot_hide_incomplete_mode,
        test_human_attestation_requires_identifier,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
