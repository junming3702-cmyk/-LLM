"""Caller-side gap ledger for a locked review question.

This module reads only the inference input. It never reads model responses,
award records, expert labels, or retrospective reference answers. An audit
row is a source-bound observation, not a legal conclusion or a gold label.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json


VERSION = "task-gap-audit-v1"
LEGAL_U_FIELDS = (
    "claim_id", "question_verbatim", "dependency_key", "missing_material",
    "material_status", "reason", "counterfactual_impact", "next_check",
)
LEGAL_U_STATUSES = frozenset({
    "confirmed_missing_from_package", "applicable_rule_unavailable",
    "decisive_fact_unknown", "future_event_unknown",
})
PROCESSING_STATUSES = frozenset({"not_in_current_input", "unreadable", "processing_failed"})
AUDIT_DEPENDENCIES = frozenset({
    "independent_applicable_rule", "grounded_comparison", "question_decisive_facts",
})


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def binding(runtime_input: dict) -> dict[str, str]:
    task = runtime_input.get("review_task_contract_v2") or {}
    return {
        "question_sha256": digest(task.get("question_verbatim")),
        "contract_evidence_sha256": digest(runtime_input.get("contract_evidence") or {}),
        "retrieved_legal_evidence_sha256": digest(runtime_input.get("retrieved_legal_evidence") or []),
        "hierarchy_retrieval_audit_sha256": digest(runtime_input.get("hierarchy_retrieval_audit") or {}),
    }


def _row(runtime_input: dict, *, dependency_key: str, missing_material: str,
         material_status: str, validated: bool, audit_locator: str,
         audit_rule_id: str, note: str) -> dict:
    task = runtime_input["review_task_contract_v2"]
    return {
        "version": VERSION, "issue_id": runtime_input["issue_id"],
        "review_question": task["question_verbatim"],
        "dependency_key": dependency_key, "missing_material": missing_material,
        "material_status": material_status, "validated": validated,
        "record_origin": "deterministic_input_audit", "audit_locator": audit_locator,
        "audit_rule_id": audit_rule_id, "note": note, **binding(runtime_input),
    }


def build_task_gap_audit(runtime_input: dict) -> list[dict]:
    """Inventory evidence boundaries before a model call, without inferring N.

    The only presently attested legal U is the narrowly locked actual-upload
    question on supplied PDF excerpts. Other issues get non-attesting rows;
    this is intentionally conservative until a separate package/source audit
    can verify a purported decisive absence or applicable-rule deficit.
    """
    task = runtime_input.get("review_task_contract_v2") or {}
    issue_id = runtime_input.get("issue_id")
    question = task.get("question_verbatim")
    required = task.get("required_for_legal_conclusion") or []
    if not issue_id or not isinstance(question, str) or not question.strip():
        raise ValueError("locked_question_required_for_task_gap_audit")
    if not isinstance(required, list) or not set(required) <= AUDIT_DEPENDENCIES:
        raise ValueError("invalid_task_dependencies")
    evidence = runtime_input.get("contract_evidence") or {}
    if not isinstance(evidence, dict):
        evidence = {}
    excerpt = evidence.get("document_excerpt") or ""
    document_id = str(evidence.get("document_id") or "")
    location = str(evidence.get("document_location") or "")
    rows = []
    if "question_decisive_facts" in required:
        # The task itself asks whether an actual upload can be established
        # solely from a PDF excerpt. No claim about the complete filing package.
        actual_upload_pdf_only = (
            task.get("declared_task_type") == "actual_conduct"
            and "仅凭现有PDF副本" in question and "完整上传加密投标文件" in question
            and "PDF" in (runtime_input.get("project_context") or {}).get("evidence_boundary", "")
            and "回执编号" not in excerpt and "上传成功时间戳" not in excerpt
        )
        if actual_upload_pdf_only:
            rows.append(_row(runtime_input, dependency_key="question_decisive_facts",
                             missing_material="实际上传完成时间戳及平台回执",
                             material_status="decisive_fact_unknown", validated=True,
                             audit_locator="review_task_contract_v2.question_verbatim + "
                                           "project_context.evidence_boundary + contract_evidence.document_id",
                             audit_rule_id="actual_upload_pdf_only_v1",
                             note="PDF摘录不能核验实际上传；只限定本题，不断言全包缺失。"))
        else:
            rows.append(_row(runtime_input, dependency_key="question_decisive_facts",
                             missing_material="当前问题所需决定性事实（未独立确认缺失）",
                             material_status="not_assessed", validated=False,
                             audit_locator=f"contract_evidence.document_location:{location}",
                             audit_rule_id="input_fact_inventory_v1",
                             note="现有文本可见不等于所需事实完整；不据此签发法律U。"))
    if "independent_applicable_rule" in required:
        rows.append(_row(runtime_input, dependency_key="independent_applicable_rule",
                         missing_material="当前问题直接适用的独立法源（未完成专项适用性判定）",
                         material_status="not_assessed", validated=False,
                         audit_locator="retrieved_legal_evidence + hierarchy_retrieval_audit",
                         audit_rule_id="law_delivery_inventory_v1",
                         note="候选法条数量或命中不证明适用，也不证明穷尽性无依据。"))
    if "grounded_comparison" in required:
        rows.append(_row(runtime_input, dependency_key="grounded_comparison",
                         missing_material="当前命题的比较对象（未独立确认缺失）",
                         material_status="not_assessed", validated=False,
                         audit_locator=f"contract_evidence.document_location:{location}",
                         audit_rule_id="comparison_inventory_v1",
                         note="比较关系由审查任务确定；不得把未见全文当作已审文件包缺失。"))
    return rows


def verified_row_matches(runtime_input: dict, basis: dict) -> bool:
    task = runtime_input.get("review_task_contract_v2") or {}
    current_binding = binding(runtime_input)
    rows = runtime_input.get("task_gap_audit") or []
    if runtime_input.get("task_gap_audit_version") != VERSION or not isinstance(rows, list):
        return False
    return any(
        isinstance(row, dict) and row.get("version") == VERSION
        and row.get("validated") is True
        and row.get("record_origin") in {"deterministic_input_audit", "human_confirmed"}
        and row.get("issue_id") == basis.get("claim_id") == runtime_input.get("issue_id")
        and row.get("review_question") == basis.get("question_verbatim") == task.get("question_verbatim")
        and row.get("dependency_key") == basis.get("dependency_key")
        and row.get("material_status") == basis.get("material_status")
        and row.get("missing_material") == basis.get("missing_material")
        and isinstance(row.get("audit_locator"), str) and bool(row["audit_locator"].strip())
        and all(row.get(key) == val for key, val in current_binding.items())
        for row in rows
    )


def prompt_addendum() -> str:
    """Generate the model-side field contract from the gate's field constants."""
    fields = ", ".join(LEGAL_U_FIELDS)
    legal = " | ".join(sorted(LEGAL_U_STATUSES))
    processing = " | ".join(sorted(PROCESSING_STATUSES))
    return f"""

## Task-aware legal-U and independent gap ledger (candidate v12)

The locked `review_task_contract_v2` is the only question being answered.
`task_gap_audit` is a CALLER-SIDE inventory, not a model answer or gold label.
Do not assert that a whole filed package lacks a page merely because the
current inference excerpt omits it. Award status is excluded and cannot be
used to infer that every clause is compliant.

For a legal U, provide `legal_u_basis` inside the finding as an OBJECT with
exactly these required nonempty string fields: {fields}. Bind `claim_id` to
runtime `issue_id` and copy `question_verbatim` character-for-character from
the locked task. `dependency_key` must be one of the locked
`required_for_legal_conclusion` values. `missing_material` and
`material_status` must match a `task_gap_audit` row that was independently
validated, source-bound, and marked `validated=true`. Legal-U statuses:
{legal}. Explain why this missing item is decisive for THIS question and what
concrete comparison becomes possible after recovery; do not merely repeat
that a coverage field is missing. A model-generated claim cannot validate
its own gap. Only emit a legal U where the audit attests the same gap.

Input transmission/OCR/protocol problems ({processing}) are NOT legal U.
Preserve the visible partial finding and identify the processing limitation;
the deterministic gate will hold delivery pending recovery. Actual-conduct
facts are outside a clause-design question even if future performance is
unknown. For a conditional tender rule, analyze its trigger -> prescribed
effect against the supplied law; do not demand evidence that a hypothetical
trigger already happened. Pure document visibility or text-to-text response
is not a legal verdict and must use the separate task route. Never select N
to avoid an audit failure: N requires affirmative within-scope comparison,
and an unresolved decisive gap must remain unresolved/held. Never auto-reject
or certify the entire project.

If there is no legal U, omit `legal_u_basis`; do not fill it with placeholder
strings. All preexisting JSON finding fields remain required by the active
compact-output contract.
"""


def attach_audit(runtime_input: dict) -> dict:
    result = deepcopy(runtime_input)
    result["task_gap_audit_version"] = VERSION
    result["task_gap_audit"] = build_task_gap_audit(result)
    result["gate_protocol_version"] = "task-aware-v1"
    return result
