"""Build an opt-in candidate; never edit the production prompt in place."""
from pathlib import Path
from nu_boundary_policy import PROMPT as NU_PROMPT

VERSION = "task-gate-v2-candidate"

def _replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Base prompt drift: candidate replacement must match exactly once")
    return text.replace(old, new, 1)

def build_prompt(base):
    text = _replace_once(base,
        "存在决定性事实、定位、适用性、版本、schema 或证据缺口，或者候选材料不能形成具体风险关系；",
        "当前审查问题存在决定性事实、适用性、版本或证据缺口；单纯未形成风险关系不等于信息不足。schema/定位校验失败须另记处理状态，不能冒充有效的法律弃答；")
    text = _replace_once(text,
        "只有在没有任何可用法规证据形成具体风险关系时，才使用 `insufficient_information_needs_human_confirm`，并将 `reasoning_conclusion` 表述为“依据当前材料无法得出确切结论”或同等强度；",
        "只在当前问题的决定性依据或事实不足时使用 `insufficient_information_needs_human_confirm`；已基于适用法条完成有定位的有限比较且无支持性冲突时，允许 N。具体法律后果不是所有文本预审问题的必需要件；")
    text = _replace_once(text,
        "附件、图纸、清单、版本或系统记录未提供，且已供原文与适用要求不足以建立具体差异；若已有明确要求与当前已审记录的差异，可作限于该记录的有限复核；",
        "附件、图纸、清单、版本或系统记录缺失，且该缺口阻断当前明确的审查问题。已审文件包确认缺失与当前输入未提供应区分记录，但决定性缺失均保留 U；不能仅以缺失本身判 R；")
    text = _replace_once(text,
        "，或虽有候选材料却没有形成具体风险关系；此时通常输出",
        "，且当前问题因此缺少决定性法源；此时输出")
    text = _replace_once(text,
        "若法规或招标文件明确要求某项资质、证书或证明文件，而投标文件明确写明“未提供”“缺失”或出现可定位的相反事实，则属于有事实支持的潜在风险；此时可输出 `requires_human_legal_review`，但必须说明最终法律后果仍需人工判断。",
        "若法规或招标文件明确要求某项资质、证书或证明文件，应区分已审包确认缺失、当前摘录未提供和有肯定事实支持的实质冲突。前两者若决定本问题均保留 U，不单凭缺失升级 R；独立支持的数值或禁止性冲突可以 R，最终法律后果仍需人工判断。")
    return text + NU_PROMPT + """

## Task-gate v2 candidate: input-bound scope and review handoff
Runtime review_task_contract_v2 preserves the exact question, excerpt hash,
stage and evidence boundary. It is machine-derived scope metadata, NOT human
approval or permission to rewrite the question. Flag scope_needs_confirmation
when ambiguous. Never infer a complete package from a partial excerpt.
For each gap explain which comparison requires the missing item. An unrelated
future act, authenticity check or other-document question is follow-up only
when it cannot change this bounded comparison. Do not hide exceptions,
decisive values, applicable legal sources or applicability behind false flags.
N still requires an independent applicable supplied rule, a grounded completed
check and adequate facts. R requires a specific supported conflict. Do not
assert authenticity or actual performance from an undertaking.
Preserve the concrete contract-versus-rule comparison and completed checks
even when the result is U. Label unverified observations as model explanations,
not admitted legal evidence. Separately state blocking gaps and next actions.
Keep the required Markdown table AND Excel-compatible structured output.
Transport, truncation, schema and provenance failures are processing failures,
not successful legal U judgments. Every conclusion requires human second
review; no automatic rejection, award or final legal decision.
"""

def candidate_prompt():
    return build_prompt((Path(__file__).resolve().parents[1] / "prompts/system_prompt_final.md").read_text(encoding="utf-8"))
