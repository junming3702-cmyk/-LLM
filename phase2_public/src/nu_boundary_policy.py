"""Opt-in question-relative answerability checks, not a legal truth oracle.

No issue IDs, human labels or project-specific answers are used. The model
provides a bounded comparison; the gate checks its scope, evidence pointers
and gap taxonomy. Semantic correctness remains subject to human review.
"""
import re

VERSION = "nu-question-boundary-v1.1"
TARGETS = {"textual_pre_review", "document_response", "document_completeness", "actual_conduct"}
TEXT_TARGETS = {"textual_pre_review", "document_response"}
HARD_GAPS = {"required_document_missing", "input_evidence_missing",
             "unreadable_evidence", "comparison_value_missing",
             "key_legal_source_missing", "decisive_applicability_missing"}
FOLLOWUP_GAPS = {"authenticity_unverified", "future_performance_unverified",
                 "other_outside_question"}

PROMPT = """
## N/U question-boundary candidate (nu-question-boundary-v1.1)
This opt-in section supersedes older blanket rules equating 'no concrete
fact-law difference' with U, or equating N with certified overall compliance.
Keep all source/provenance, local applicability and human review safeguards.

N means no supported issue found in the SUPPLIED review question, after an
adequate, evidence-grounded bounded check. It does not prove authenticity,
actual submission, future performance, universal legality or exhaustive search.
U means the supplied question cannot be answered because a DECISIVE fact,
applicable rule, comparison value, required document or readable evidence is
missing. Confirmed missing material in an examined package AND material not
provided in the current input both remain U, distinguished in explanation.
Do not promote document absence alone to R. A supported substantive numerical
or prohibitory conflict may remain R; do not disguise such a conflict as N.

First separate clause/statement wording, documentary completeness and actual
conduct. Authenticity or future execution is not automatically decisive for
wording pre-review. If a document merely states an obligation, do not demand
proof of its future execution merely to assess that wording. Conversely,
do not silently narrow a completeness, qualification or factual-verification
question into a wording-only question to obtain N. Legal consequences need
not be proved when the question concerns only textual compatibility.

For N, identify at least one completed check grounded in an actually supplied
applicable independent legal provision. A general/unrelated clause, no hit,
or only supplementary material is NOT enough. If the decisive law is absent,
keep U even if there is no detected conflict. Preserve conditions, exceptions,
negations, subject and stage. Different wording or a broader set is not by
itself a legal conflict or proof of legality. Do not invent a required document.

Earlier triage 'missing_elements' are candidate questions, not independently
confirmed decisive gaps. Reassess their relevance to the supplied question,
without changing the executed retrieval audit or denying a real evidence gap.

For EACH finding add decision_basis exactly as follows:
{
  "review_question": "copy project_context.review_question exactly",
  "review_target": "textual_pre_review | document_response | document_completeness | actual_conduct",
  "answerability": "sufficient | decisive_gap",
  "completed_checks": [
    {"check": "specific check completed", "document_quote": "exact supplied excerpt substring",
     "document_locator": "one exact supplied source locator",
     "legal_chunk_ids": ["actually cited independent chunk id"],
     "comparison": "explain document vs supplied rule for this check"}
  ],
  "gaps": [
    {"kind": "required_document_missing | input_evidence_missing | unreadable_evidence | comparison_value_missing | key_legal_source_missing | decisive_applicability_missing | authenticity_unverified | future_performance_unverified | other_outside_question",
     "detail": "specific unavailable item", "blocks_current_question": true,
     "reason": "why its absence prevents this question, or why it is outside the question"}
  ],
  "bounded_conclusion": "substantive conclusion limited to this question"
}
Use document_response for assessing what a supplied response document states;
it does not by itself establish actual submission or performance. Keep missing
required response material decisive, and never rename a completeness question.
completed_checks may be empty for U, but not for N. Every genuine U needs a
specific gap, not merely 'cannot form a conflict'. Generic follow-up requests
must not be labelled key-source/input gaps unless necessary for this question.
For authenticity/future-performance outside textual pre-review, set
blocks_current_question=false with a specific reason; never use false to hide
a decisive gap. Unknown actual facts remain decisive in actual-conduct tasks.
Use compliance_relation=explicitly_satisfied for a positive matched comparison,
or no_supported_conflict_within_scope for a sufficient bounded non-conflict
check. Missing/non-applicable liability elements do not themselves imply U.
Keep the canonical N/R/U conclusion codes, one finding per supplied issue,
the required fact-law comparison and concrete human follow-up. No final bid
rejection/award decision. All output remains requires_human_second_review.
"""


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def audit_basis(runtime, finding, usable_evidence):
    """Validate structure/binding. Never call this a legal correctness check."""
    from scope_boundary_policy import task_contract
    task = task_contract(runtime)
    question = _text(task.get("question"))
    contract = runtime.get("contract_evidence") or {}
    excerpt = _text(contract.get("document_excerpt"))
    location = _text(contract.get("document_location"))
    locators = {x.strip() for x in location.split(";") if x.strip()}
    locators.update(re.findall(r"\[([^\]\n]+)\]", excerpt))
    marked_spans = {}
    markers = list(re.finditer(r"\[([^\]\n]+)\]", excerpt))
    for i, marker in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(excerpt)
        marked_spans.setdefault(marker.group(1), []).append(excerpt[marker.end():end])
    basis = finding.get("decision_basis")
    result = {"version": VERSION, "schema_valid": True,
              "eligible_no_issue": False, "force_insufficient": False,
              "blocking_reasons": [], "follow_up_only": [],
              "completed_check_count": 0, "legal_correctness_verified": False,
              "task_type": task["task_type"], "review_question": question}
    errors = []
    if not isinstance(basis, dict):
        basis = {}; errors.append("decision_basis_missing")
    if not question or basis.get("review_question") != question:
        errors.append("review_question_not_bound")
    target = basis.get("review_target")
    if target not in TARGETS:
        errors.append("invalid_review_target")
    if basis.get("answerability") not in {"sufficient", "decisive_gap"}:
        errors.append("invalid_answerability")
    if not _text(basis.get("bounded_conclusion")):
        errors.append("bounded_conclusion_missing")
    task_type = task["task_type"]
    if task_type == "unknown":
        result["blocking_reasons"].append("runtime_task_scope_unknown")
    if task_type == "actual_conduct" and target != "actual_conduct":
        result["blocking_reasons"].append("actual_question_narrowed_to_text")
    if task_type == "document_completeness" and target != "document_completeness":
        result["blocking_reasons"].append("completeness_question_narrowed_to_text")
    if task_type == "clause_design" and target != "textual_pre_review":
        result["blocking_reasons"].append("wording_question_expanded")
    if target in TEXT_TARGETS and re.search(
            r"(?:是否实际|是否真实|核实.{0,8}真实性|核验.{0,8}真实性|是否已提交|是否齐全|是否完整提交)", question):
        result["blocking_reasons"].append("explicit_factual_question_narrowed")
    gaps = basis.get("gaps")
    if not isinstance(gaps, list):
        gaps = []; errors.append("gaps_not_list")
    for gap in gaps:
        if not isinstance(gap, dict):
            errors.append("invalid_gap"); continue
        kind = gap.get("kind"); blocking = gap.get("blocks_current_question")
        if kind not in HARD_GAPS | FOLLOWUP_GAPS or type(blocking) is not bool or not _text(gap.get("detail")) or not _text(gap.get("reason")):
            errors.append("invalid_gap_contract"); continue
        if kind in HARD_GAPS or blocking or target not in TEXT_TARGETS:
            result["blocking_reasons"].append(kind + ": " + gap["detail"])
        else:
            result["follow_up_only"].append({"kind": kind, "detail": gap["detail"], "reason": gap["reason"]})
    if basis.get("answerability") == "decisive_gap":
        result["blocking_reasons"].append("model_reports_question_decisive_gap")
        if not gaps:
            errors.append("decisive_gap_without_description")
    checks = basis.get("completed_checks")
    if not isinstance(checks, list):
        checks = []; errors.append("completed_checks_not_list")
    valid_ids = {e.get("chunk_id") for e in usable_evidence}
    for check in checks:
        if not isinstance(check, dict):
            errors.append("invalid_completed_check"); continue
        quote = _text(check.get("document_quote")); locator = _text(check.get("document_locator"))
        ids = check.get("legal_chunk_ids")
        wrong_span = locator in marked_spans and not any(quote in span for span in marked_spans[locator])
        if (len(quote) < 4 or quote not in excerpt or locator not in locators or wrong_span
                or not isinstance(ids, list) or not ids or not all(isinstance(x, str) and x in valid_ids for x in ids)
                or not _text(check.get("check")) or not _text(check.get("comparison"))):
            result["blocking_reasons"].append("completed_check_not_grounded")
        else:
            result["completed_check_count"] += 1
    requested_n = finding.get("conclusion_type") == "no_supported_issue_found_within_review_scope"
    if requested_n and not checks:
        result["blocking_reasons"].append("no_completed_check_for_N")
    if requested_n and not usable_evidence:
        result["blocking_reasons"].append("no_independent_applicable_basis_for_N")
    result["schema_errors"] = errors
    result["schema_valid"] = not errors
    result["force_insufficient"] = bool(errors or result["blocking_reasons"])
    result["eligible_no_issue"] = bool(requested_n and target in TEXT_TARGETS
        and basis.get("answerability") == "sufficient" and result["completed_check_count"]
        and not result["force_insufficient"])
    result["bounded_conclusion"] = _text(basis.get("bounded_conclusion"))
    return result
