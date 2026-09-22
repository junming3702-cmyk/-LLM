"""Opt-in Phase 2 applicability/task experiment. No labels, API or corpus writes.

Filtering is candidate admission, not legal validity adjudication. The manifest
is bound to the frozen source hash and an in-corpus scope paragraph. It adds
metadata only; it never adds a legal provision or upgrades source authority.
"""
from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import dataclass, field
import re

VERSION = "scope-boundary-v1"
ARMS = {"baseline": (False, False), "geo_only": (True, False),
        "task_only": (False, True), "geo_task": (True, True)}
LOCAL_CLASSES = {"local_regional", "local", "regional", "local_regulation"}
UNKNOWN = {"", "unknown", "uncertain", "unverified_local_scope",
           "verified_local_scope", "source_geographic_scope_not_stated"}
PROVINCES = ("北京市", "天津市", "上海市", "重庆市", "河北省", "山西省", "辽宁省",
             "吉林省", "黑龙江省", "江苏省", "浙江省", "安徽省", "福建省", "江西省",
             "山东省", "河南省", "湖北省", "湖南省", "广东省", "海南省", "四川省",
             "贵州省", "云南省", "陕西省", "甘肃省", "青海省", "台湾省", "内蒙古自治区",
             "广西壮族自治区", "西藏自治区", "宁夏回族自治区", "新疆维吾尔自治区",
             "香港特别行政区", "澳门特别行政区")


@dataclass(frozen=True)
class ScopePolicy:
    geographic_filter: bool = False
    task_boundary: bool = False
    source_scopes: dict = field(default_factory=dict)

    @classmethod
    def for_arm(cls, name, source_scopes=None):
        geo, task = ARMS[name]
        return cls(geo, task, source_scopes or {})

    def flags(self):
        return {"version": VERSION, "geographic_filter": self.geographic_filter,
                "task_boundary": self.task_boundary, "corpus_expansion": False}


def normalize_place(value):
    text = re.sub(r"\s+", "", str(value or ""))
    for name in PROVINCES:
        stem = re.sub(r"特别行政区|壮族自治区|回族自治区|维吾尔自治区|自治区|省|市", "", name)
        if text in {name, stem}:
            return name
    return text


def make_scope_registry(corpus):
    """One deliberately narrow, source-bound overlay for the current corpus.

    This is not an online source manifest and not an authority/temporal check.
    Unknown documents must supply explicit metadata or remain quarantined.
    """
    records = {}
    for row in corpus:
        title = str(row.get("title") or row.get("law") or "")
        quote = str(row.get("text") or row.get("legal_quote") or "")
        anchor = "在四川省行政区域内从事建筑活动的当事人应当遵守本条例"
        if title.startswith("四川省建筑管理条例") and anchor in quote and row.get("file_hash") and row.get("source_id"):
            records[str(row["source_id"])] = {
                "file_hash": row["file_hash"], "province": "四川省",
                "project_type_scope": "construction_activity",
                "scope_anchor_chunk_id": row.get("chunk_id"),
                "scope_anchor_locator": row.get("source_locator"),
                "scope_anchor_quote": anchor,
                "provenance": "frozen_corpus_scope_paragraph_no_new_law",
                "temporal_validity_verified": False,
            }
    return records


def _source_scope(source, registry):
    entry = registry.get(str(source.get("source_id")), {})
    if entry and str(entry.get("file_hash", "")).lower() == str(source.get("file_hash", "")).lower():
        return deepcopy(entry), "hash_bound_corpus_scope"
    geo = source.get("geographic_scope")
    scope = dict(geo) if isinstance(geo, dict) else {}
    if isinstance(geo, str) and geo not in UNKNOWN:
        normalized = normalize_place(geo)
        if normalized in PROVINCES:
            scope["province"] = normalized
        elif geo in {"national", "nationwide", "全国", "中国全国"}:
            scope["national"] = True
        # Unstructured composite geography is not guessed.
    if source.get("project_type_scope"):
        scope["project_type_scope"] = source["project_type_scope"]
    title = str(source.get("title") or source.get("law") or source.get("source_title") or "")
    declared = [name for name in PROVINCES if title.startswith(name)]
    if not declared:
        declared = [name for name in PROVINCES if title.startswith(normalize_place(name).removesuffix("市")) and name.endswith("市")]
    if declared:
        title_province = declared[0]
        if scope.get("province") and normalize_place(scope["province"]) != title_province:
            scope["conflict"] = True
        if scope.get("national"):
            scope["conflict"] = True
        scope.setdefault("province", title_province)
    return scope, "runtime_metadata_or_local_title"


def geographic_decision(source, context, registry=None):
    scope, origin = _source_scope(source, registry or {})
    local = (source.get("normative_level") == "Level 4"
             or source.get("scope_classification") in LOCAL_CLASSES
             or bool(scope.get("province") or scope.get("city") or scope.get("county")))
    result = {"version": VERSION, "chunk_id": source.get("chunk_id"),
              "allowed": True, "reason": "nonlocal_unchanged", "is_local": local,
              "scope_origin": origin, "source_scope": scope,
              "normative_authority_changed": False, "temporal_validity_checked": False}
    if not local:
        return result
    result["allowed"] = False
    loc = context.get("project_location") or {}
    if not isinstance(loc, dict):
        result["reason"] = "project_location_invalid"
        return result
    if scope.get("conflict"):
        result["reason"] = "source_scope_conflicting"
        return result
    if loc.get("human_confirmation") != "confirmed":
        result["reason"] = "project_location_unconfirmed"
        return result
    municipality = normalize_place(loc.get("city"))
    if municipality in {"北京市", "天津市", "上海市", "重庆市"} and loc.get("province") and normalize_place(loc["province"]) != municipality:
        result["reason"] = "project_location_conflicting"
        return result
    country = str(loc.get("country") or "")
    if country and country not in {"中国", "中华人民共和国", "China", "CN", "PRC"}:
        result["reason"] = "country_mismatch_or_unresolved"
        return result
    dimensions = [key for key in ("province", "city", "county") if scope.get(key)]
    if not dimensions:
        result["reason"] = "local_source_scope_unknown"
        return result
    for key in dimensions:
        if not loc.get(key):
            result["reason"] = "project_" + key + "_missing"
            return result
        if normalize_place(loc[key]) != normalize_place(scope[key]):
            result["reason"] = "geographic_mismatch_" + key
            return result
    project_type = str(context.get("project_type") or "").strip()
    if not project_type or project_type in UNKNOWN:
        result["reason"] = "project_type_missing"
        return result
    types = scope.get("project_type_scope")
    if types == "construction_activity":
        positive = bool(re.search(r"施工|建筑工程|建设工程|construction_project|construction_activity", project_type))
        ambiguous_or_nonconstruction = bool(re.search(r"非施工|非建筑|不涉及|不包含|咨询|服务|货物采购", project_type))
        type_match = positive and not ambiguous_or_nonconstruction
    elif types in ("all", "all_project_types"):
        type_match = True
    elif isinstance(types, list):
        type_match = project_type in types
    else:
        type_match = bool(types and types not in UNKNOWN and types == project_type)
    if not type_match:
        result["reason"] = "source_project_type_unmatched_or_unknown"
        return result
    result.update(allowed=True, reason="geography_and_project_type_matched")
    return result


def annotate_admitted(source, decision):
    row = deepcopy(source)
    row["geographic_filter_decision"] = decision
    if decision["is_local"] and decision["allowed"]:
        row.update(scope_classification="local_regional",
                   geographic_scope={k: v for k, v in decision["source_scope"].items() if k in {"province", "city", "county"}},
                   project_type_scope=decision["source_scope"]["project_type_scope"],
                   applicability_basis="地域与工程类型匹配；不证明时点效力、全部适用条件或事实—法条关系。")
        # Only close a spatial-pending status. Never overwrite a source denial.
        if row.get("applicability_status") in {None, "", "pending_source_scope_match", "source_applicability_not_explicitly_stated"}:
            row["applicability_status"] = "matched"
    return row


class ContextFilteredRetriever:
    """Per-request copy; filter full level pools BEFORE BM25/dense top-K/RRF.

    Shares immutable embeddings/model, never changes the caller's corpus/index.
    The baseline ranking implementation remains the sole ranking implementation.
    """
    def __init__(self, base, context, policy):
        self.delegate = copy(base)
        self.delegate.corpus = list(base.corpus)
        self.delegate.level_phase_indices = {}
        self.audit = []
        for key, indices in base.level_phase_indices.items():
            admitted = []
            for index in indices:
                decision = geographic_decision(base.corpus[index], context, policy.source_scopes)
                if decision["is_local"]:
                    self.audit.append({**decision, "level": key[0], "phase": key[1]})
                if decision["allowed"]:
                    admitted.append(index)
                    if decision["is_local"]:
                        self.delegate.corpus[index] = annotate_admitted(base.corpus[index], decision)
            self.delegate.level_phase_indices[key] = admitted

    def __getattr__(self, name):
        return getattr(self.delegate, name)


TASK_PROMPT = """
## Opt-in task-boundary experiment (runtime scope, not answer labels)
Use review_task_contract to distinguish clause design/pre-review from checking
an actual submitted response, document completeness or actual conduct. A
promise/template is not proof of actual conduct; an unshown attachment is not
proof of non-submission. Do not require an actual rejected bidder or actual
opening event merely to review the wording of a proposed clause. For each
finding add claim_scope: clause_design | document_response |
document_completeness | actual_conduct. Preserve all conjunctive conditions,
exceptions, negations, stages and triggering facts in the law AND the clause.
If a trigger is unknown, stop that factual conclusion; if a trigger is absent,
do not claim that the conditional obligation has been breached. A clause may
still need a distinct design review. Use only supplied, applicable law. An
internal textual inconsistency is an observation, NOT proof of illegality.
Only facts decisive for the supplied question may cause abstention; list their
relation to the question. Do not fabricate a missing fact, a requirement, or a
no-issue conclusion. Keep the existing human-review states and output schema.
"""


def task_contract(runtime, *, question_intent=None):
    ctx = runtime.get("project_context") or runtime.get("runtime_project_context") or {}
    contract = runtime.get("contract_evidence") or {}
    stage = str(ctx.get("document_stage") or "")
    types = []
    if re.search(r"招标文件.*(?:预审|条款)|条款预审|clause_pre_review", stage):
        types.append("clause_design")
    if re.search(r"投标文件|响应文件|比选申请|document_response", stage):
        types.append("document_response")
    if re.search(r"完整性审查|document_completeness", stage):
        types.append("document_completeness")
    if re.search(r"实际履行|行为核验|performance_verification", stage):
        types.append("actual_conduct")
    # An explicit leading task code owns the task classification. Narrative
    # boundaries such as "不证明实际履行" must not create a second, affirmative
    # actual-conduct task. Conflicting *explicit codes* still fail closed.
    codes = {'clause_pre_review':'clause_design','document_response':'document_response',
             'document_completeness':'document_completeness','performance_verification':'actual_conduct'}
    leading = re.match(r'^(clause_pre_review|document_response|document_completeness|performance_verification)(?=[:：\s]|$)',stage)
    explicit_codes = set(re.findall(r'\b(?:clause_pre_review|document_response|document_completeness|performance_verification)\b',stage))
    task = (codes[leading[1]] if leading and len(explicit_codes)==1 else
            'unknown' if leading else types[0] if len(types)==1 else 'unknown')
    question = str(ctx.get("review_question") or "")
    conflict = bool(re.search(r"是否实际|实际开标|实际履行|是否已提交|是否已送达", question))
    if question_intent is not None:
        from question_scope_signals import legacy_conflict_active
        conflict = legacy_conflict_active(question, question_intent)
    if task == "clause_design" and conflict:
        task = "unknown"  # Explicit question/stage conflict cannot relax a gap.
    return {"version": VERSION, "task_type": task, "stage_source": stage,
            "question": ctx.get("review_question", ""),
            "evidence_boundary": ctx.get("evidence_boundary", ""),
            "document_id": contract.get("document_id"),
            "document_location": contract.get("document_location"),
            "classification_basis": "runtime_document_stage_and_question_conflict_check_no_expert_labels",
            "actual_performance_proven": False,
            "decisive_fact_policy": "required_for_this_question_not_all_possible_legal_consequences"}


def boundary_audit(runtime, finding, bounded, *, question_intent=None):
    task = task_contract(runtime, question_intent=question_intent)
    updated = deepcopy(bounded)
    contract = runtime.get("contract_evidence") or {}
    fact = str(contract.get("document_excerpt") or "")
    audit = {**task, "ignored_nondecisive_gaps": [], "force_insufficient": False,
             "observations": [], "requires_human_review": True,
             "legal_risk_established_by_this_module": False}
    claim = finding.get("claim_scope")
    if claim and claim not in {"clause_design", "document_response", "document_completeness", "actual_conduct"}:
        audit["force_insufficient"] = True
        audit["reason"] = "invalid_claim_scope"
    elif claim and (task["task_type"] == "unknown" or (claim == "actual_conduct" and task["task_type"] != "actual_conduct")):
        audit["force_insufficient"] = True
        audit["reason"] = "claim_exceeds_declared_review_task"
    if task["task_type"] == "clause_design" and claim != "actual_conduct":
        gap = "实际开标时间与投标截止时间，以及对应预定地点"
        # Narrow repair: a *normative future clause* does not require an event
        # record. A clause alone does not prove that opening actually complied.
        if re.search(r"(?:应当|应|必须|须).{0,30}(?:开标|一致)|开标.{0,30}(?:应当|必须|应).{0,30}一致", fact):
            if gap in updated.get("missing_decisive_facts", []):
                updated["missing_decisive_facts"] = [x for x in updated["missing_decisive_facts"] if x != gap]
                audit["ignored_nondecisive_gaps"].append({"gap": gap, "reason": "clause_design_not_actual_event_verification"})
        compact = re.sub(r"\[[^\]]+\]|\s+", "", fact)
        if re.search(r"不指定出具保函.{0,15}(?:金融|担保)机构", compact) and re.search(r"(?:银行保函.{0,8})?必须为基本账户银行出具", compact):
            audit["observations"].append({"kind": "documentary_inconsistency_only",
                "description": "前后文字分别不指定保函机构、要求基本账户银行出具，需核对条款优先顺序。",
                "document_location": contract.get("document_location"),
                "legal_conclusion": "not_established_without_direct_applicable_rule"})
    return audit, updated


def prepare_runtime(runtime, policy):
    result = deepcopy(runtime)
    if not (policy.geographic_filter or policy.task_boundary):
        return result
    result["scope_boundary_experiment"] = policy.flags()
    if policy.geographic_filter:
        admitted, excluded = [], []
        for row in result.get("retrieved_legal_evidence", []):
            decision = geographic_decision(row, result.get("project_context") or {}, policy.source_scopes)
            if decision["allowed"]:
                admitted.append(annotate_admitted(row, decision))
            else:
                excluded.append(decision)
        result["retrieved_legal_evidence"] = admitted
        result["geographic_admission_audit"] = {"excluded": excluded, "corpus_expansion": False}
        # A filtered-out source cannot be republished through an alternate list.
        result["external_sources_used"] = [r for r in result.get("external_sources_used", [])
            if geographic_decision(r, result.get("project_context") or {}, policy.source_scopes)["allowed"]]
    if policy.task_boundary:
        result["review_task_contract"] = task_contract(result)
    return result
