"""Render private P3 analyses without reading source contracts or identities."""
import argparse
import json
from pathlib import Path


def pct(value):return '—' if value is None else f'{value:.1%}'


def report(analyses):
    lines=['# P3 外部检索闭环：隔离对照结果','','## Material Passport','',
        '- ARS experiment-agent；validate；Verification Status: ANALYZED。',
        '- 公开法规与用户批准的合成任务；不是新专家盲评，也不使用真实合同。',
        '- 原始语料、专家底稿及生产版本未覆盖；本轮方法为隔离候选。','',
        '## 如何读本报告','',
        'R＝需要人工法律复核/确认的风险；N＝审查范围内未发现有依据的问题；U＝信息不足。',
        '失败单元保留在22条分母，不计作正确的U；8条工程故障不纳入法律判断分母。',
        'A为本地，B为历史固定来源访问，B-matched为同来源页面访问，C为条款发现＋有条件重推理。',
        '每条任务共用一次本地生成，四组观察不是四组独立样本。B是当前URL-only实现，不能当作强外部RAG竞争基线。',
        'natural不作全局剔除，但仍遵守任务本身的候选可见性；controlled_gap额外人为移除预先登记的条款，两者不可合并。','']
    for a in analyses:
        label=a['corpus_mode']; agg=a['aggregates'];req=a['request_audit']
        lines += [f'## {label} 条件','',f"参考分布：{a['reference_verdict_counts']}。",'',
            '|条件|语义一致/22|原始LLM一致/22|完成数|N→R误报|U被升级N/R|新增final调用|',
            '|---|---:|---:|---:|---:|---:|---:|']
        for arm,d in agg.items():
            lines.append(f"|{arm}|{d['semantic_agreement_count']}/22|{d['raw_semantic_agreement_count']}/22|{d['status_counts'].get('completed',0)}|{d['N_to_R']}|{d['U_to_decision']}|{d['actual_new_final_generations']}|")
        pairs=a['paired_A_C']; improved=[r['issue_id'] for r in pairs if r['change']=='improved']; worse=[r['issue_id'] for r in pairs if r['change']=='worsened']
        lines += ['',f"A→C参考一致性：改善{len(improved)}条（{', '.join(improved) or '无'}）；下降{len(worse)}条（{', '.join(worse) or '无'}）。",'',
            '### 外部检索阶段指标（条件性，不能冒充全模型Recall/MRR）','',
            '|排名口径|有已登记相关条文且实际触发复检的任务数|宏平均法条Recall@5|MRR（返回排名）|',
            '|---|---:|---:|---:|']
        for stage in ('candidate','admitted'):
            d=a['conditional_external_retrieval'][stage]
            m='—' if d['mrr_over_returned_ranking'] is None else f"{d['mrr_over_returned_ranking']:.4f}"
            lines.append(f"|{stage}|{d['denominator']}|{pct(d['macro_evidence_recall_at_5'])}|{m}|")
        lines += ['', 'candidate为前10候选中前5的已登记条文覆盖；admitted为准入后压缩排名。两者分母相同，但排名含义不同，不能把人工准入压缩后的高分宣传成自动检索提升。',
            '未触发复检的任务不在这项条件性检索指标分母；原本没有相关条文的任务也不当作100%召回。当前缺少经过核验的本地chunk—外部整条法条共同相关性映射，因此不报告端到端统一Recall/MRR。','',
            '### 调用与成本边界','',
            f"- 实际DeepSeek请求：{req['calls']}；报告token总量：{req['usage'].get('total_tokens',0):,}。",
            f"- 实验墙钟：{req['wall_seconds']:.1f}秒；逐请求耗时中位数：{req['request_median_seconds']:.3f}秒（含triage和final混合，不能当作单条审查耗时）。",
            f"- 返回模型名称：`{json.dumps(req['returned_model_names'],ensure_ascii=False)}`；请求名称为deepseek-v4-flash，未独立认证服务端alias。",
            '- 外部法规使用冻结快照，实际网站HTTP请求为0；不证明网站当前在线或法条当前效力。',
            '- 缓存命中和请求组合可能不同；不宣称总体效率提升，不推算未经核实的金额。',
            f"- 请求字段泄漏检查通过：{req['runtime_leak_scan_passed']}；自动重试0次。",'',
            '### 逐条对照','', '|单元|参考|A|B|B-matched|C|C新增生成|', '|---|---|---|---|---|---|---|']
        for d in a['details']:
            states=[(v['verdict'] or v['status']) for v in d['arms'].values()]
            lines.append('|'+ '|'.join([d['issue_id'],d['reference_verdict'],*states,str(d['arms']['C_article_discovery']['new_final_generation'])])+'|')
        lines += ['',f"分析来源run-manifest SHA256：`{a['run_manifest_sha256']}`。",'']
    lines += ['## 必须保留的限制与11项方法风险检查','',
        '|检查|本轮处理|','|---|---|',
        '|辛普森悖论|分别保留语料条件、family与逐条结果，不只看总平均。|',
        '|生态谬误|合成单元不是独立项目，也不能推断真实市场用户。|',
        '|选择偏差/Berkson|用户批准的新编任务、同一法规与近邻family；不宣称人群代表性。|',
        '|碰撞变量偏差|外部指标条件于初步U，仅作阶段诊断，不据此作总体因果判断。|',
        '|基率忽视|展示R/N/U分布；不把合成风险比例当作真实发生率。|',
        '|回归均值|不用挑选最差单元补跑的结果证明提升；失败照实保留。|',
        '|幸存者偏差|全部22任务纳入结论分母，失败与U分列。|',
        '|多重寻找|不作显著性筛选、不挑最好条件隐去其余条件。|',
        '|分析路径自由度|初次适配故障批次和修正记录保留；修正轮为开发后验证。|',
        '|相关≠因果|两种语料状态分别分析；B→C是实现组合差异，不是纯算法因果效果。|',
        '|反向因果|冻结方案在运行前登记，但任务已知且有开发暴露，不能称确认性独立验证。|',
        '', '覆盖：11/11检查。未计算p值或独立同分布置信区间；不伪造统计显著性。',
        'LLM可复现性：N/A（外部随机API单次主尝试）；可核验的是请求/结果/证据与版本溯源。',
        '', '全部判断仍须人工二次审核。既有专家B分数不转移到本轮模型；不代替最终法律或招投标决定。','']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser();p.add_argument('--analysis',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    content=report([json.loads(path.read_text('utf-8')) for path in a.analysis])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as h:h.write(content)
    print(str(a.output))


if __name__=='__main__':main()
