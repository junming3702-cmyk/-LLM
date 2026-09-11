"""Explicit denominators; evaluator-only reference consumption; no model calls."""
from __future__ import annotations
from collections import Counter
from experiment_integrity import semantic_verdict


def retrieval_metrics(ranked_ids, reference_ids, *, k=5, reference_set_complete=False):
    if k < 1:
        raise ValueError("k must be positive")
    if len(ranked_ids) != len(set(ranked_ids)):
        raise ValueError("duplicate retrieved IDs: fix ranking, do not silently change ranks")
    refs = set(reference_ids)
    if not refs:
        return {"scorable": False, "reason": "no_reference_evidence", "hit_at_k": None,
                "reference_evidence_recall_at_k": None, "reciprocal_rank": None,
                "complete_necessary_evidence_recall_at_k": None}
    matched = refs.intersection(ranked_ids[:k])
    first = next((i for i, x in enumerate(ranked_ids, 1) if x in refs), None)
    recall = len(matched) / len(refs)
    return {"scorable": True, "k": k, "retrieved_reference_count": len(matched),
            "reference_count": len(refs), "hit_at_k": int(bool(matched)),
            "reference_evidence_recall_at_k": recall,
            "complete_necessary_evidence_recall_at_k": recall if reference_set_complete else None,
            "reference_set_complete": reference_set_complete,
            "reciprocal_rank": 1 / first if first else 0,
            "reciprocal_rank_search_depth": len(ranked_ids)}


def rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def pair_metrics(enrollment, observations):
    """Missing/failed/blocked runs remain in the pre-enrolled denominator.

    All inputs here are evaluator data. No module calling a model imports labels.
    Each enrollment row is one predeclared baseline/variant comparison, not a
    statistically independent project. No significance claim is made.
    """
    by_id = {}
    for row in observations:
        key = row["observation_id"]
        if key in by_id:
            raise ValueError("duplicate observation: do not choose the better response")
        by_id[key] = row
    counters = Counter()
    details = []
    seen_pairs = set()
    for pair in enrollment:
        if pair["pair_id"] in seen_pairs:
            raise ValueError("duplicate pair_id")
        seen_pairs.add(pair["pair_id"])
        if pair.get("verification_status") != "human_verified":
            raise ValueError("unverified expected relation cannot enter formal metrics")
        base = by_id.get(pair["original_observation_id"], {})
        variant = by_id.get(pair["variant_observation_id"], {})
        good = base.get("execution_status") == variant.get("execution_status") == "completed"
        bv, vv = base.get("verdict"), variant.get("verdict")
        pair_correct = bool(good and bv in pair["original_allowed_verdicts"] and vv in pair["variant_allowed_verdicts"])
        relation = pair["expected_relation"]
        if relation not in {"same", "decisive_change", "safe_missing"}:
            raise ValueError("unknown relation")
        relation_ok = bool(good and bv == vv) if relation == "same" else pair_correct
        counters["pairs"] += 1
        counters["pair_correct"] += int(pair_correct)
        counters["original_correct"] += int(base.get("execution_status") == "completed" and bv in pair["original_allowed_verdicts"])
        counters[relation + "_total"] += 1
        counters[relation + "_success"] += int(relation_ok)
        counters["missing_or_noncompleted"] += int(not good)
        details.append({"pair_id": pair["pair_id"], "mother_case_id": pair["mother_case_id"],
                        "project_id": pair.get("project_id"), "pair_correct": pair_correct,
                        "relation_satisfied": relation_ok, "both_completed": good})
    return {"pairs": counters["pairs"],
            "mother_cases": len({p["mother_case_id"] for p in enrollment}),
            "pair_correctness": rate(counters["pair_correct"], counters["pairs"]),
            "original_correctness_pair_weighted": rate(counters["original_correct"], counters["pairs"]),
            "missing_or_noncompleted_pairs": counters["missing_or_noncompleted"],
            "relations": {r: rate(counters[r + "_success"], counters[r + "_total"])
                          for r in ("same", "decisive_change", "safe_missing")},
            "details": details, "inference": "descriptive_only_no_independence_assumed"}


def intervention_observation(observation_id, result, *, before_gate=False):
    from experiment_integrity import result_status
    status = result_status(result)
    response = (result.get("final_llm_response") or {}).get("parsed") if before_gate else (result.get("post_llm_gate") or {}).get("response")
    findings = response.get("findings", []) if isinstance(response, dict) else []
    if not isinstance(findings, list):
        findings = []
    # One issue is the evaluator's unit. Multi-finding aggregation needs a new protocol.
    verdict = semantic_verdict(findings[0].get("conclusion_type")) if len(findings) == 1 and isinstance(findings[0], dict) else None
    execution = status["execution_status"]
    if before_gate and execution == "gate_blocked":
        execution = "completed" if verdict else "invalid_output"
    if verdict is None and execution == "completed":
        execution = "invalid_output"
    return {"observation_id": observation_id, "verdict": verdict if execution == "completed" else None,
            "execution_status": execution, "stage": "raw" if before_gate else "gated"}
