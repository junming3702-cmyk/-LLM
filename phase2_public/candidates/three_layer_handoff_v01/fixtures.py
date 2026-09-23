"""Entirely fictional fixtures, not statutes, projects or historical answers."""
from copy import deepcopy
from spec import VERSION, TASK_MODES, digest
from gate import seal_context

def context(two=False):
    texts = ["我方承诺提供两次检查服务。", "本合成条款规定仅一次检查。", "金额为8单位，基数B未给出。"]
    sources = [{"source_id": "S"+str(i), "document_sha256": digest("synthetic_document"),
                "locator": "SYN:p"+str(i), "text": t} for i, t in enumerate(texts, 1)]
    evidence = [{"evidence_id": "E"+str(i), "source_id": s["source_id"],
                 "document_sha256": s["document_sha256"], "locator": s["locator"], "quote": s["text"]}
                for i, s in enumerate(sources, 1)]
    task = {
        "question": "比对合成承诺条款与合成规范的文本关系。",
        "review_mode": "clause_design", "review_target": "textual_pre_review", "document_stage": "clause_pre_review",
        "excluded_dependencies": ["actual_performance"],
        "required_claims": [{"claim_id": "C1", "description": "确认合成文本的有界要求",
                             "required_dependencies": ["applicable_rule", "current_clause_context", "readability"]}],
    }
    if two:
        task["required_claims"].append({"claim_id": "C2", "description": "按合成公式核对金额上限",
                                       "required_dependencies": ["applicable_rule", "comparison_operand", "regulatory_applicability"]})
    laws = [{"chunk_id": "LAW-S1", "text": "虚构测试规则：承诺两次检查；金额上限为B的10%。",
             "source_sha256": digest("fictional_rule"), "locator": "SYN-RULE:1", "admitted": True,
             "independent_legal_basis": True, "applicability_status": "applicable", "temporal_status": "valid"}]
    return seal_context({"task": task, "sources": sources, "evidence_registry": evidence, "laws": laws})

def claim(cid, state="assessed", checks=None, observations=None, gaps=None):
    return {"claim_id": cid, "assessment_state": state,
            "finding": "no_supported_issue" if state == "assessed" else None,
            "check_ids": checks or [], "observation_ids": observations or [], "gap_ids": gaps or [],
            "rationale": "只记录锁定子问题；尚未完成的部分不声称已完成。"}

def check(cid="CK1", claim_id="C1", observation=False, refs=None):
    return {"check_id": cid, "check_kind": "text_observation" if observation else "legal_comparison",
            "check": "合成文本对照", "document_evidence_refs": refs or ["E1"],
            "legal_chunk_ids": [] if observation else ["LAW-S1"],
            "claim_ids": [] if observation else [claim_id],
            "comparison": "原文承诺两次，与合成规则两次一致；不认证未来实际执行。"}

def gap(gid="G1", dep="comparison_operand", cid="C2", conflict=False, outside=False, unknown=False):
    from spec import DEPENDENCIES
    return {"gap_id": gid, "kind": DEPENDENCIES[dep][0], "dependency_key": dep,
            "detail": "后续实际履行情况" if outside else "缺少基数B" if dep == "comparison_operand" else "缺少用于解释两处文本关系的材料",
            "task_relation": "outside_locked_scope" if outside else "undetermined" if unknown else "decisive_for_claim",
            "affected_claim_ids": [] if outside else [cid],
            "reason": "影响被指定的子结论；范围外事项不影响本次已锁定文本比较。" if outside else "该材料决定当前子问题能否得到有界判断。",
            "counterfactual_impact": "本次只检查承诺文本，不核验以后行为。" if outside else "缺少材料，不能完成指定的解释或数值比较。",
            "dependency_trigger": "explicit_scope_exclusion" if outside else "observed_context_conflict" if conflict else "undetermined" if unknown else "locked_requirement",
            "trigger_refs": [{"type": "check", "id": "O1"}] if conflict else [],
            "next_step": "请人工补充所列材料并按锁定问题复核。"}

def response(ctx):
    return {"protocol_version": VERSION, "task_scope_sha256": ctx["task_scope_sha256"],
            "input_sha256": ctx["input_sha256"], "review_question": ctx["task"]["question"],
            "review_target": ctx["task"]["review_target"], "claim_assessments": [],
            "completed_checks": [], "gaps": []}

def complete():
    ctx = context()
    r = response(ctx)
    r["claim_assessments"] = [claim("C1", checks=["CK1"])]
    r["completed_checks"] = [check()]
    return ctx, r
def partial():
    ctx = context(two=True)
    r = response(ctx)
    r["claim_assessments"] = [claim("C1", checks=["CK1"]),
                               claim("C2", "blocked_by_decisive_gap", observations=["O1"], gaps=["G1"])]
    r["completed_checks"] = [check(), check("O1", observation=True, refs=["E3"])]
    r["gaps"] = [gap()]
    return ctx, r

def blocked():
    ctx, r = partial()
    r["claim_assessments"][0] = claim("C1", "blocked_by_decisive_gap", observations=["O1"], gaps=["G2"])
    r["completed_checks"] = [check("O1", observation=True, refs=["E1", "E2"])]
    r["gaps"].append(gap("G2", "current_clause_context", "C1", conflict=True))
    return ctx, r

def outside():
    ctx, r = complete()
    r["gaps"] = [gap(dep="actual_performance", outside=True)]
    return ctx, r

def rebind(ctx, r):
    ctx = seal_context(ctx)
    r.update(task_scope_sha256=ctx["task_scope_sha256"], input_sha256=ctx["input_sha256"],
             review_question=ctx["task"]["question"], review_target=ctx["task"]["review_target"])
    return ctx, r
