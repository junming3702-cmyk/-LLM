"""Render completed descriptive results; no online calls or model changes."""
from pathlib import Path
import argparse
import json

NAMES={'baseline':'原版','geo_only':'仅地域过滤','task_only':'仅任务边界','geo_task':'两项合用'}


def pct(value): return '不可估计' if value is None else f'{100*value:.1f}%'
def num(value): return '未报告' if value is None else f'{value:,.1f}'


def table(headers, rows):
    clean=lambda v:str(v).replace('|','\\|').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(map(clean,headers))+' |',
        '| '+' | '.join('---' for _ in headers)+' |']+
        ['| '+' | '.join(map(clean,row))+' |' for row in rows])


def render(d):
    if not d['completion']['complete_attempts']: raise ValueError('unfinished batch')
    arms=list(NAMES)
    n=d['summary']['baseline']['gated']['all']['planned_n']
    out=['# 第一阶段独立实验：地域适用性过滤与审查任务边界修复',
        '## Material Passport',
        '- 来源：绑定运行日志、冻结共同输入、离线阶段A参照。\n'
        '- 状态：已执行的开发侧描述性对照；不是新专家验证，不是独立留出验证。\n'
        '- 原始专家评分、历史输出、生产版本及法规库不由本报告修改。',
        '## 1. 对照设计',
        f'{n}条审查单元 × 4组 = {4*n}次计划输出。每组均重新调用同一模型，'
        '不是用旧输出替代同期对照。四组固定法规库、共同输入、embedding、TopK和模型参数；'
        '仅改变地域过滤、任务约束两个因素。本轮新增法条数为0，所有组外部检索关闭。',
        f"模型：`{d['run_manifest']['binding']['requested_model']}`。"
        '执行顺序按输入序号循环轮转，并非随机分组；每个单元、每个条件仅生成一次。',
        '## 2. 主结果：全部计划样本计入分母',
        'N=限定审查范围内未发现有依据的问题；R=有依据的风险；U=信息或依据不足。'
        '运行失败不是U。参照不一致不自动证明模型或专家错误。',
        table(['组别','阶段','完成数','一致数/计划数','一致率','非弃权覆盖','非弃权一致率','N→R','R→N','U→N/R'],[
            [NAMES[a],'原始' if s=='raw' else '闸门后',m['completed_count'],f"{m['match_count']}/{m['planned_n']}",
             pct(m['agreement_all_planned']),pct(m['nonabstained_coverage']),pct(m['selective_agreement']),
             m['false_R_from_N'],m['false_N_from_R'],m['unsupported_upgrade_from_U']]
            for a in arms for s in ('raw','gated') for m in [d['summary'][a][s]['all']]]),
        '弃权能降低错误升级，也可能降低可用性，因此一致率、覆盖率和选择性一致率必须共同阅读。',
        '## 3. 两项改动的分离效果',
        table(['配对比较（闸门后）','改善','恶化','正确性不变','一致率差/百分点'],[
            [NAMES[c['to']]+' − '+NAMES[c['from']],c['counts'].get('improved',0),c['counts'].get('worsened',0),
             c['counts'].get('unchanged_correctness',0),f"{100*c['agreement_delta']:+.1f}"]
            for c in d['contrasts'] if c['stage']=='gated']),
        '这里的“改善/恶化”仅指相对于冻结A参照的逐条正确性变化。两组均错误但错误类别不同，仍计为正确性不变。',
        f"交互差值（闸门后，合用−仅任务−仅地域+原版）：{100*d['interaction_agreement_difference']['gated']:+.1f}个百分点。"
        '这是一次生成下的描述性差值，不是统计显著性或稳定因果效应。',
        '## 4. 地方法规使用边界',
        table(['组别','最终证据包不适用地方条目','涉及单元','最终引用不适用条目','涉及单元'],[
            [NAMES[a],x['packet_ineligible_local_entries'],x['packet_affected_units'],x['unsafe_citation_entries'],x['unsafe_citation_units']]
            for a in arms for x in [d['source_safety'][a]]]),
        '这是依据既定地域/工程类型匹配规则进行的软件诊断，统计的是条目及涉及单元，'
        '不等于对全部法规的法律适用性作了人工裁决。软件测试的过滤保证与实际LLM引用行为分别检验。',
        '## 5. 三个项目分开报告',
        table(['组别','项目','一致数/计划数','一致率','完成数'],[
            [NAMES[a],p,f"{m['match_count']}/{m['planned_n']}",pct(m['agreement_all_planned']),m['completed_count']]
            for a in arms for p,m in d['summary'][a]['gated']['projects'].items()]),
        '审查单元嵌套于3个项目，不把45条当作45个独立工程样本。不据此宣称跨地区、跨项目总体泛化。',
        '## 6. 运行成本与效率',
        table(['组别','API请求','输入token','输出token','单元中位秒','单元P90秒','无usage请求'],[
            [NAMES[a],c['provider_attempts'],c['usage_totals'].get('prompt_tokens','未报告'),
             c['usage_totals'].get('completion_tokens','未报告'),num(c['per_unit_wall_seconds']['median']),
             num(c['per_unit_wall_seconds']['p90_nearest_rank']),c['calls_without_usage']]
            for a in arms for c in [d['efficiency'][a]]]),
        f"并发批次墙钟总时间：{d['completion']['elapsed_seconds']/60:.1f}分钟。"
        '逐单元用时包括检索及推理，受并发、缓存、服务端负载影响；各组用时之和不等于批次墙钟时间。'
        'token不直接换算未核对的费用；没有新专家用时测量，不能宣称人工审核节时。',
        '## 7. 失败、闸门及任务范围',
        table(['组别','闸门前后观察发生变化','长度截断数','主分析状态统计'],[
            [NAMES[a],d['task_adherence'][a]['gate_changed_observation_count'],d['task_adherence'][a]['length_truncations'],
             json.dumps(d['summary'][a]['gated']['all']['status_counts'],ensure_ascii=False)] for a in arms]),
        '仅传输失败项可另做一次同参数补跑敏感性分析；本表保留首轮失败。'
        '长度截断、结论错误、过度报警或格式失败不按结果挑选重跑。',
        '## 8. 当前可支持和不可支持的结论',
        '可支持：两项修复已在独立候选实现中接线，并在固定C0库的四条件实验中留下可核查结果。'
        '改善与恶化均保留；不能因某组总分更高就忽略错误升级、覆盖率下降或服务失败。',
        '不可支持：这次对照不能证明补库收益、外部检索收益、人工审核满意度提升，'
        '也不能将新输出套用原阶段B专家评分。REAL45缺少穷尽且独立核验的相关法条集合，'
        '因此本轮不产生新的Recall@5或MRR。历史合成集检索指标不可移植成当前真实项目指标。',
        '后续定向补库必须保留独立C1来源清单，并固定审查方法另做C0/C1比较。'
        '不能把同时加入法规、地域过滤及新提示词的一次总提升归功于任一单项。',
        '## 9. 可追溯绑定',
        table(['对象','SHA256'],[
            ['共同运行输入',d['run_manifest']['binding']['input_sha256']],
            ['冻结C0法规库',d['run_manifest']['binding']['corpus_sha256']],
            ['正式提示词',d['run_manifest']['binding']['prompt_sha256']],
            ['任务边界附加约束',d['run_manifest']['binding']['task_overlay_sha256']],
            ['离线A参照',d['reference_file_sha256']]]),
        '逐条输出、请求、usage、闸门动作和引用证据的哈希见私有分析文件及审阅表。'
        '本报告和真实项目摘录不进入公开GitHub，仅通用模型代码及合成测试可公开。']
    return '\n\n'.join(out)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    d=json.loads(a.analysis.read_text(encoding='utf-8'))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:f.write(render(d))
    print('REPORT_WRITTEN '+str(a.output))


if __name__=='__main__':main()
