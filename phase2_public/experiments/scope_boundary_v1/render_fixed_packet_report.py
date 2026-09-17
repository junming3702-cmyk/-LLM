"""Render a completed private analysis; not legal advice or journal inference."""
from pathlib import Path
import argparse
import json


def percent(x):
    return '不可计算' if x is None else f'{x*100:.1f}%'


def render(a):
    if not a['completion']['complete_attempts']:
        raise ValueError('full batch not complete')
    labels={'original_prompt':'原提示词','binding_prompt':'候选提示词'}
    gates={'raw':'原始生成','original_gate':'旧闸门','binding_gate':'候选闸门'}
    lines=['# 固定证据包：提示词与风险绑定闸门对照', '',
        '本报告是开发集机制对照，不是独立外部验证，不沿用旧专家B评分。', '',
        '## 材料与版本', '',
        f"- 运行标识：`{a['manifest']['binding']['run_id']}`。",
        '- 45个审查单元来自3个项目，每单元两种提示词各一次新生成；同一原始响应分别经过两种确定性闸门。',
        '- 各提示词组的主分母均为45，失败保留。四种闸门观察不等于180个独立样本。',
        '- 使用原geo_task固定证据包；没有重新检索、定向补库、外部检索或OCR。',
        '- 实际请求中的证据包、提示词和模型参数已逐请求核对；参考答案仅在离线统计读取。',
        f"- 模型：`{a['manifest']['binding']['requested_model']}`；输出上限16384；temperature 0.1；thinking enabled/low。",
        '', '## 主要结果', '',
        '|提示词|观察层|有效/45|参照一致/45|一致率|N误报为R|R误判为N|非弃答覆盖|风险精确率|风险召回|',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for arm in labels:
        for gate in gates:
            m=a['summary'][arm][gate]['all']
            lines.append(f"|{labels[arm]}|{gates[gate]}|{m['completed_count']}|{m['match_count']}|{percent(m['agreement_all_planned'])}|{m['false_R_from_N']}|{m['false_N_from_R']}|{percent(m['nonabstained_coverage'])}|{percent(m['risk_precision'])}|{percent(m['risk_recall'])}|")
    lines+=['', '风险召回是参照R病例中被识别为R的比例，不是检索Recall@5。N为限定审查范围内未发现支持性风险，R为需要人工复核/确认，U为依据不足。', '',
        '## 配对变化', '', '|比较|观察层|改善|变差|正确性不变|一致率差（百分点）|', '|---|---|---:|---:|---:|---:|']
    for c in a['contrasts']:
        label=(labels.get(c.get('prompt_arm'),'')+'：' if c.get('prompt_arm') else '')+c['from']+' → '+c['to']
        counts=c['counts']
        lines.append(f"|{label}|{c['stage']}|{counts.get('improved',0)}|{counts.get('worsened',0)}|{counts.get('unchanged_correctness',0)}|{100*c['agreement_delta']:+.2f}|")
    lines+=['', '## 生成效率与失败', '', '|提示词|请求数|报告总token|未报告usage的请求|单元耗时中位数/秒|P90/秒|', '|---|---:|---:|---:|---:|---:|']
    for arm,e in a['efficiency'].items():
        wall=e['unit_wall_seconds']
        lines.append(f"|{labels[arm]}|{e['provider_attempts']}|{e['usage_totals'].get('total_tokens','未报告')}|{e['calls_without_usage']}|{wall['median']:.2f}|{wall['p90_nearest_rank']:.2f}|")
    lines+=['', f"批次墙钟：{a['completion']['elapsed_seconds']/60:.2f}分钟。并发请求耗时之和不等于批次墙钟；本表仅比较最终推理，不代表端到端RAG效率。未按token推断账单金额。", '',
        '|提示词|单元|生成状态|finish_reason|', '|---|---|---|---|']
    for d in a['detail']:
        if d['observations']['raw']['status']!='completed':
            lines.append(f"|{labels[d['arm']]}|{d['unit_id']}|{d['observations']['raw']['status']}|{d['finish_reason']}|")
    lines+=['', '## 结论边界', '',
        '- 数据已用于发现问题和开发规则，不能宣称独立泛化；三个项目不支撑广泛总体显著性推断。',
        '- 拦截风险并转为U不等于正确识别N；一致率、错误报警和弃答覆盖必须同时阅读。',
        '- 结构性法条绑定只是必要条件，不是法律语义正确性的充分证明；所有输出仍需人工二次审核。',
        '- 未补库、未测新检索相关性标签，不报告新的Recall@5/MRR。后续补库C0/C1必须单独比较。',
        '- 不以这轮结果自动替换专家评价的生产版本。', '']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    a=json.loads(args.analysis.read_text(encoding='utf-8'))
    content=render(a)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as handle: handle.write(content)
    print(str(args.output))


if __name__=='__main__': main()
