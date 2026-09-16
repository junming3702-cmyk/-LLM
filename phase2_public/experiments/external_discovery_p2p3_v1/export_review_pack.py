"""Render public candidate records for human review; never fills approval fields."""
import argparse
import json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--reports', nargs='+', type=Path, required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if args.out.exists(): raise ValueError('output_exists')
    lines=['# P2新候选条文：人工准入审阅包', '',
           '这不是已确认法规库。P1已批准的10条不自动替代本包的新条文、版本与适用范围确认。',
           '以下是按主题筛选的候选，排序仅表示词项匹配，不是适用性或法律判断；罚则、定义及关联规定可能同时出现。',
           '如与本次任务无关可拒绝，无需为全部候选补齐准入。仅已确认的必要条文才能进入独立实验快照。', '',
           '每条请核对：正式来源、完整原文、版本、生效起止、地域/采购制度/项目类型、条件/例外/交叉引用。',
           '确认时使用别名即可，无须公开个人身份。确认记录存本地，不推送公开仓库。', '']
    count=0
    for path in args.reports:
        report=json.loads(path.read_text('utf-8'))
        lines += [f"## 查询：{' / '.join(report['public_terms'])}", '', f"项目上下文：`{json.dumps(report['context'],ensure_ascii=False)}`", '']
        for p in report['candidates']:
            count+=1
            lines += [f"### {count}. {p['law_title']} · {p['article']}", '',
                      f"来源：[官方候选页面]({p['source_url']})", '',
                      f"候选版本：{p['version_label']}；实际层级：{p['actual_normative_level']}；地域：{p['geographic_scope']}", '',
                      f"候选ID：`{p['candidate_id']}`", f"原始快照SHA256：`{p['raw_snapshot_sha256']}`", f"条文SHA256：`{p['article_sha256']}`", '',
                      f"定位（本地规范化快照偏移，不是物理页码）：`{json.dumps(p['source_locator'],ensure_ascii=False)}`", '',
                      '```text', p['legal_quote'], '```', '',
                      '人工决定：□确认 □修改 □拒绝；确认者别名：____；确认日期时间：____', '',
                      '版本来源核验：____；适用起始日：____；失效日（如有）：____；核验覆盖至：____', '',
                      '地域/项目类型/采购制度：____；必要定义、条件、例外、交叉引用：____', '',
                      '当前事实是否足以判断适用性：____；备注：____', '']
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'candidates':count,'approvals_written':0,'file':str(args.out)},ensure_ascii=False))

if __name__=='__main__':main()
