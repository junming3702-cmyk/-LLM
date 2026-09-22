"""Single source of truth for the v4.1 decision_basis wire protocol.

This deliberately small schema dialect is validated below, not advertised as
full JSON Schema. It governs protocol structure, never legal entailment.
"""
from copy import deepcopy
import json

VERSION = "scope-dependency-v4.1-candidate"
DEPENDENCIES = {
    "submission_package_completeness": ["input_evidence_missing", "required_document_missing"],
    "authenticity": ["authenticity_unverified"],
    "actual_performance": ["future_performance_unverified"],
    "current_clause_context": ["input_evidence_missing", "required_document_missing"],
    "applicable_rule": ["key_legal_source_missing"],
    "regulatory_applicability": ["decisive_applicability_missing"],
    "comparison_operand": ["comparison_value_missing"],
    "readability": ["unreadable_evidence"],
    "other_undetermined": ["material_type_undetermined"],
}


def field(type_, description, enum=None, optional=False):
    value = {"type": type_, "description": description, "required": not optional}
    if enum is not None:
        value["enum"] = enum
    return value


SCHEMA = {
    "version": VERSION,
    "dependency_kind_pairs": DEPENDENCIES,
    "basis": {
        "review_question": field("text", "原样复制已锁定问题。"),
        "review_target": field("text", "对应锁定任务模式。", ["textual_pre_review", "document_response", "document_completeness", "actual_conduct"]),
        "answerability": field("text", "关系未解决必须用 scope_unresolved，而非法律 U。", ["sufficient", "decisive_gap", "scope_unresolved"]),
        "task_scope_sha256": field("text", "原样复制 review_task_contract_v41.input_scope_sha256。"),
        "completed_checks": field("checks", "已完成观察/法规比对；U 可为空，不伪造完成项。"),
        "gaps": field("gaps", "每项仅一种材料依赖；混合事项拆开，未知保持未知。"),
        "bounded_conclusion": field("text", "当前问题内的实质结论，不证明总体合规。"),
    },
    "check": {
        "check_id": field("text", "本单元内唯一检查编号。"),
        "check_kind": field("text", "观察不作为独立法律依据。", ["text_observation", "legal_comparison"]),
        "check": field("text", "必须填写具体检查名称；comparison不能代填。"),
        "document_quote": field("text", "所给原文精确引用；多片段为逐项换行连接。"),
        "document_locator": field("text", "精确定位；多片段定位用分号连接。"),
        "legal_chunk_ids": field("strings", "只填实际准入的法条；观察必须为空数组。"),
        "claim_ids": field("strings", "对应 required_claims；观察必须为空，法规比对不可为空。"),
        "comparison": field("text", "具体说明原文与要求的相同/差异及适用前提，不能只列法条。"),
        "document_fragments": field("fragments", "可选，跨段时每段单独精确定位，2–8项。", optional=True),
    },
    "fragment": {
        "document_quote": field("text", "单一片段精确原文。"),
        "document_locator": field("text", "该片段唯一输入定位。"),
    },
    "gap": {
        "gap_id": field("text", "本单元内唯一缺口编号。"),
        "kind": field("text", "材料/证据状态，不使用范围外作为材料类型。", sorted({x for v in DEPENDENCIES.values() for x in v})),
        "dependency_key": field("text", "缺失材料所属的一种依赖。", list(DEPENDENCIES)),
        "detail": field("text", "只说明缺什么，不混合整包、真实性、补遗、金额等不同事项。"),
        "task_relation": field("text", "为什么与锁定任务有关。", ["decisive_for_claim", "outside_locked_scope", "undetermined"]),
        "affected_claim_ids": field("strings", "决定性缺口须绑定已声明且需要该依赖的子结论。"),
        "blocks_current_question": field("bool", "必须与任务关系一致；false 不构成放行依据。"),
        "reason": field("text", "说明该材料与当前子结论的关系，不写泛泛补查理由。"),
        "counterfactual_impact": field("text", "若材料缺失/补全，哪一步判断不能完成/会改变；范围外说明为何不改变当前比对。"),
        "dependency_trigger": field("text", "来源是任务明确要求、已观察冲突还是泛化猜测。", ["locked_requirement", "observed_context_conflict", "explicit_scope_exclusion", "generic_unverified_possibility", "undetermined"]),
        "trigger_evidence": field("pointers", "观察到具体冲突时必须给出原文定位；其他情形可为空数组。"),
    },
    "gate_owned_output_groups": ["blocking_gap", "out_of_scope_item", "scope_review_item"],
    "mechanical_aliases": {"check": {"check_name": "check"}},
}


def _validate_record(obj, record, path):
    errors = []
    if not isinstance(obj, dict):
        return [path + ":expected_object"]
    fields = SCHEMA[record]
    for key in obj:
        if key not in fields:
            errors.append(path + "." + key + ":unknown_field")
    for key, rule in fields.items():
        here = path + "." + key
        if key not in obj:
            if rule["required"]:
                errors.append(here + ":required")
            continue
        value, type_ = obj[key], rule["type"]
        if type_ == "text":
            valid = isinstance(value, str) and bool(value.strip())
        elif type_ == "bool":
            valid = type(value) is bool
        elif type_ == "strings":
            valid = isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)
            if valid and len(value) != len(set(value)):
                errors.append(here + ":duplicate_items")
        else:
            valid = isinstance(value, list)
            if valid:
                nested = {"checks": "check", "gaps": "gap", "fragments": "fragment", "pointers": "fragment"}[type_]
                for i, item in enumerate(value):
                    errors += _validate_record(item, nested, here + "[" + str(i) + "]")
                if type_ == "fragments" and not 2 <= len(value) <= 8:
                    errors.append(here + ":requires_2_to_8_fragments")
        if not valid:
            errors.append(here + ":invalid_" + type_)
        elif "enum" in rule and value not in rule["enum"]:
            errors.append(here + ":invalid_enum")
    if record == "gap":
        dep, kind = obj.get("dependency_key"), obj.get("kind")
        if isinstance(dep, str) and dep in DEPENDENCIES and kind not in DEPENDENCIES[dep]:
            errors.append(path + ":gap_dependency_kind_mismatch")
    return errors


def validate_basis(basis):
    return _validate_record(basis, "basis", "decision_basis")


def response_protocol_report(raw):
    """Protocol conformance only, not full application-schema/semantic pass."""
    findings = raw.get("findings") if isinstance(raw, dict) else None
    if not isinstance(findings, list) or not findings:
        return {"valid": False, "findings": [], "errors": ["findings_missing_or_empty"]}
    rows = [{"index": i, "errors": validate_basis(f.get("decision_basis") if isinstance(f, dict) else None)}
            for i, f in enumerate(findings)]
    return {"valid": all(not x["errors"] for x in rows), "findings": rows, "errors": []}


def normalize_response(raw, enabled=False):
    """No generated text, reclassification, gap removal, or guessed defaults."""
    output = deepcopy(raw)
    audit = {"enabled": enabled, "actions": [], "raw": response_protocol_report(raw)}
    if enabled and isinstance(output, dict) and isinstance(output.get("findings"), list):
        for i, finding in enumerate(output["findings"]):
            basis = finding.get("decision_basis") if isinstance(finding, dict) else None
            if not isinstance(basis, dict):
                continue
            records = [("basis", basis, "findings[" + str(i) + "].decision_basis")]
            for plural, singular in (("completed_checks", "check"), ("gaps", "gap")):
                items = basis.get(plural)
                if isinstance(items, list):
                    records += [(singular, item, records[0][2] + "." + plural + "[" + str(j) + "]")
                                for j, item in enumerate(items) if isinstance(item, dict)]
            for kind, record, path in records:
                for old, new in SCHEMA["mechanical_aliases"].get(kind, {}).items():
                    if old in record and new not in record:
                        record[new] = record.pop(old)
                        audit["actions"].append({"path": path, "operation": "rename_field", "from": old, "to": new})
                for name, rule in SCHEMA[kind].items():
                    value = record.get(name)
                    if "enum" in rule and isinstance(value, str):
                        canonical = value.strip().lower()
                        if canonical in rule["enum"] and canonical != value:
                            record[name] = canonical
                            audit["actions"].append({"path": path + "." + name, "operation": "enum_case_whitespace", "from": value, "to": canonical})
    audit["normalized"] = response_protocol_report(output)
    audit["raw_response_modified"] = False
    audit["semantic_repairs_permitted"] = False
    return output, audit


def render_schema():
    return json.dumps(SCHEMA, ensure_ascii=False, indent=2, sort_keys=True)
