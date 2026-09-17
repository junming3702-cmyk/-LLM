"""Prepare fact-only P3 runtime from the already approved synthetic task snapshot.

No expected conclusion, reference provision, family or fault instruction is
placed in LLM input. Test controls stay in a separate operator-side file.
This is a transparent input transformation, not fresh human adjudication.
"""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from experiment_integrity import validate_runtime, write_new_json, file_digest, digest
from discovery import canonical_hash

# These are frozen dataset transformations, NEVER rules in the model/gate.
# Full original synthetic task descriptions are retained in a private audit.
FACTS = {
 'P3-01':'合成合同允许无施工资质主体借用其他公司的资质承揽施工。',
 'P3-02':'合成材料已核验承包人资质与承揽范围相符；未发现借用资质证据。',
 'P3-03':'仅有报价摘要，未提供资质页；未确认是否已完整取得投标文件。',
 'P3-04':'合同明确允许施工总承包单位把全部主体结构施工交由分包单位完成。',
 'P3-05':'仅非主体专项工程分包给资质已确认适配的单位，建设单位已认可，总包保留主体结构施工；未发现再分包。',
 'P3-06':'拟分包工程尚无范围清单，无法判断其是否属于主体结构，亦未附认可记录。',
 'P3-07':'合同明确要求承包单位将全部工程转包给第三人，承包人仅收管理费。',
 'P3-08':'合同约定材料由承包单位采购，另一条要求只能购自发包单位指定供应商；未提供另外的特殊法律依据。',
 'P3-09':'仅见材料品牌表，未说明材料由谁采购。',
 'P3-10':'已确认不属限额以下小型工程，亦无依法批准开工报告；拟在领取施工许可证前开始施工。',
 'P3-11':'已提供依法按规定权限和程序批准的开工报告；未另领施工许可证。',
 'P3-12':'工程发生于2018年6月1日。当前材料未提供历史法条版本核对记录。',
 'P3-13':'政府采购服务项目仅凭行业协会推荐信替代全部供应商法定资格核验。',
 'P3-14':'普通私人企业自行购买咨询服务，并非已确认的政府采购。',
 'P3-15':'政府采购服务项目联合体缺联合协议附件；当前提供材料不完整。',
 'P3-16':'工程所在地为广东省，待审材料没有进一步给出具体的涉嫌违规条款。',
 'P3-17':'工程地点未提供，待审材料没有进一步给出具体的涉嫌违规条款。',
 'P3-18':'仅有采购金额和日期，未知是否国家投资工程及工程类型。',
 'P3-19':'2026年工程拟以2000年旧规的规模标准作为判断招标范围的唯一依据；未提供其他版本材料。',
 'P3-20':'工程发生年份未知；待审项目涉及招标规模标准。',
 'P3-21':'合同只讨论标书封面配色的审美。',
 'P3-22':'当前材料仅有工程计价相关行业实务解读，未提供具体合同条款。',
 **{f'P3-{i:02d}':'待审材料未提供可识别的合同条款或足以判断供应商资格的项目事实。' for i in range(23,31)},
}

QUESTIONS = {
 'P3-02':'仅审查承包人资质与承揽范围是否匹配。',
 'P3-11':'仅审查已有依法批准开工报告、但未另领施工许可证这一状态。',
 'P3-12':'核对工程发生时点与所取得法规版本的适用关系。',
 'P3-16':'检查所获地方性依据能否用于该工程所在地。',
 'P3-17':'检查所获地方性依据能否用于工程地点未提供的情形。',
 'P3-18':'检查所获地方性依据能否用于工程类型未明确的情形。',
 'P3-19':'核对当前项目引用招标规模标准的版本和时点。',
 'P3-20':'核对招标规模标准的时点适用条件。',
}

# Explicit task metadata, derived from the original task text, never outcomes.
# The previous generic stage made the task-boundary classifier return unknown
# even for an explicitly proposed contract clause. Keep v1 artifacts immutable.
CLAUSE_CASES = {'P3-01','P3-04','P3-07','P3-08','P3-13','P3-21'}
RESPONSE_CASES = {'P3-02','P3-05','P3-06','P3-09','P3-11','P3-14'}
COMPLETENESS_CASES = {'P3-03','P3-15'}


def task_stage(uid):
    if uid in CLAUSE_CASES: return 'clause_pre_review：合成合同条款设计预审，不证明实际履行'
    if uid in RESPONSE_CASES: return 'document_response：仅核对合成材料明确记载的状态'
    if uid in COMPLETENESS_CASES: return 'document_completeness：合成材料完整性审查，非完整项目文件'
    if uid == 'P3-10': return 'performance_verification：拟开工状态核验，不推定已实际开工'
    return '合成材料限定问题预审；版本或适用性未确定时保持任务边界'


def compile_inputs(spec, approval):
    spec_hash=canonical_hash(spec)
    if approval.get('task_spec_sha256') != spec_hash or approval.get('status')!='all_listed_articles_admitted':
        raise ValueError('existing task/source approval binding required')
    if set(FACTS)!={t['id'] for t in spec['tasks']}: raise ValueError('unexpected task coverage')
    rows,fixtures,contexts,transforms=[],[],{},[]
    for task in spec['tasks']:
        uid=task['id']
        ctx={**spec['default_context'],**task.get('context',{})}
        bound={**ctx,'scope_id':approval['scope_id'],'task_spec_sha256':spec_hash,'issue_id':uid}
        location={'country':'中国','province':ctx.get('jurisdiction'),
            'human_confirmation':'confirmed' if ctx.get('jurisdiction') else 'not_provided',
            'source':'user-approved synthetic task context; not real-project verification'}
        runtime_ctx={'project_location':location,
            'project_type_code':ctx.get('project_type'),
            'project_type':{'construction':'建筑施工工程（合成）','services':'服务采购（合成）','goods':'货物采购（合成）'}.get(ctx.get('project_type'),'unknown'),
            'procurement_regime':ctx.get('procurement_regime'),'review_as_of':ctx.get('as_of'),
            'document_stage':task_stage(uid),
            'review_question':QUESTIONS.get(uid,'仅审查所示文本与可用法规依据之间的关系。'),
            'evidence_boundary':'合成材料；仅限明确提供的事实，不代表完整项目文件。'}
        row={'issue_id':uid,'project_id':'P3-SYNTHETIC','document_id':'SYN-'+uid,
            'document_location':'approved synthetic task '+uid+' / fact-only transformation v3',
            'document_excerpt':FACTS[uid],'runtime_project_context':runtime_ctx,
            'retrieval_queries':task['terms'],'external_legal_query_terms':task['terms']}
        validate_runtime(row)
        rows.append(row)
        contexts[uid]=bound
        fixtures.append({'issue_id':uid,'fault':task.get('fault'),
            'external_only_candidate_constraint':task.get('category') in ('wrong_jurisdiction','missing_location','missing_type','expired_version','wrong_time','missing_time','supplement_only'),
            'engineering_only':bool(task.get('fault')),
            'source_class_hint':'supplement_only' if task.get('category')=='supplement_only' else None})
        transforms.append({'issue_id':uid,'original_description':task['text'],'fact_only_text':FACTS[uid],
            'task_stage':runtime_ctx['document_stage'],'input_transform_version':'v3-explicit-type-and-task-metadata',
            'runtime_row_sha256':digest(row),'raw_task_description_sha256':digest(task['text']),
            'synthetic_protocol_case':bool(task.get('fault')),
            'new_human_verification_claimed':False})
    return rows,fixtures,contexts,transforms


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--frozen',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    read=lambda name:json.loads((a.frozen/name).read_text(encoding='utf-8'))
    spec=read('task_spec.snapshot.json');approval=read('approval_record.private.json')
    rows,fixtures,contexts,transforms=compile_inputs(spec,approval)
    write_new_json(a.output/'runtime_rows.private.json',rows)
    write_new_json(a.output/'execution_fixtures.private.json',fixtures)
    write_new_json(a.output/'context_bindings.private.json',contexts)
    write_new_json(a.output/'input_transform_audit.private.json',transforms)
    write_new_json(a.output/'preparation.json',{'task_spec_sha256':canonical_hash(spec),
        'original_approval_sha256':file_digest(a.frozen/'approval_record.private.json'),
        'runtime_sha256':file_digest(a.output/'runtime_rows.private.json'),
        'rows':len(rows),'engineering_fault_tasks':sum(r['engineering_only'] for r in fixtures),
        'reference_labels_loaded':False,'source_gold_ids_in_runtime':False,
        'original_files_modified':False,'model_calls':0,'new_human_approval_claimed':False,
        'remaining':'validate candidate constraints/fault injection and matched A/B/C executor before live reasoning'})
    print('PREPARED facts-only runtime; labels and test instructions excluded; zero model calls')


if __name__=='__main__': main()
