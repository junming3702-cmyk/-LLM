// Offline review workbook. Input is private prepared data; never commit it.
import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const [input, outputDir] = process.argv.slice(2);
if (!input || !outputDir) throw new Error('Usage: export_task_gate_review.mjs input.json NEW_OUTPUT_DIR');
await fs.mkdir(path.dirname(path.resolve(outputDir)), { recursive: true });
await fs.mkdir(outputDir, { recursive: false });
const data = JSON.parse(await fs.readFile(input, 'utf8'));
const wb = Workbook.create();
const summary = wb.worksheets.add('结果对照');
const handoff = wb.worksheets.add('审查交接');
const evidence = wb.worksheets.add('证据全文');
const segments = [];
const safe = v => {
  // Do not alter literal document text with visible quote prefixes. This
  // artifact renderer fails closed on formula-leading values; the compatible
  // Python exporter supports them through explicit Excel string cell types.
  if (typeof v === 'string' && v.startsWith('=')) throw new Error('Literal formula-leading text: use the string-cell compatibility exporter');
  return v;
};
const renderText = v => typeof v === 'boolean' ? (v ? '是' : '否') : v;
const compact = data.handoff_rows.map(row => row.map((v, j) => {
  if (typeof v !== 'string' || v.length <= 180) return v;
  const chunks = Array.from(v); // Unicode-safe and lossless segmentation.
  for (let k=0;k<chunks.length;k+=180) segments.push([row[0],data.handoff_headers[j],k/180+1,chunks.slice(k,k+180).join('')]);
  return `见证据全文：${data.handoff_headers[j]}（${Math.ceil(chunks.length/180)}段）`;
}));

function setup(sheet, lastCol, endRow) {
  sheet.showGridLines=false;
  sheet.getRangeByIndexes(0,0,endRow,lastCol).format.font={name:'Arial',size:10,color:'#202D3A'};
  sheet.getRangeByIndexes(0,0,endRow,lastCol).format.verticalAlignment='top';
}
function table(sheet, row, headers, records, name, widths) {
  const matrix=[headers,...records.map(r=>r.map(v=>safe(renderText(v))))];
  const range=sheet.getRangeByIndexes(row-1,0,matrix.length,headers.length);
  range.values=matrix;range.format.wrapText=true;
  const h=sheet.getRangeByIndexes(row-1,0,1,headers.length);
  h.format={fill:'#233D57',font:{name:'Arial',size:10,color:'#FFFFFF',bold:true},wrapText:true,verticalAlignment:'center',horizontalAlignment:'center',rowHeight:34};
  let n=headers.length, col='';
  while(n){col=String.fromCharCode(65+(n-1)%26)+col;n=Math.floor((n-1)/26);}
  const t=sheet.tables.add(`A${row}:${col}${row+matrix.length-1}`,true,name);t.showFilterButton=true;
  widths.forEach((w,i)=>sheet.getRangeByIndexes(row-1,i,matrix.length,1).format.columnWidth=w);
  sheet.freezePanes.freezeRows(row);sheet.freezePanes.freezeColumns(1);
  return range;
}

setup(summary,15,60);
summary.getRange('A2').values=[['Task-gate v2 离线复核']];summary.getRange('A2').format.font={name:'Arial',size:14,bold:true};
summary.getRange('A3').values=[['固定原始响应，仅回放gate；不是新一轮LLM推理或专家评价。全部结果须人工二次审核。']];
summary.getRange('A5:F8').values=[['范围','总数','原gate匹配','候选匹配','原一致率','候选一致率'],['REAL45',data.comparison_rows.length,null,null,null,null],['REAL30',data.comparison_rows.filter(r=>r[1]==='REAL30').length,null,null,null,null],['P2',data.comparison_rows.filter(r=>r[1]==='P2').length,null,null,null,null]];
const start=13,end=start+data.comparison_rows.length-1;
summary.getRange('C6:F6').formulas=[[`=SUM(K${start}:K${end})`,`=SUM(L${start}:L${end})`,'=C6/B6','=D6/B6']];
summary.getRange('C7:F7').formulas=[[`=SUMIFS(K${start}:K${end},B${start}:B${end},A7)`,`=SUMIFS(L${start}:L${end},B${start}:B${end},A7)`,'=C7/B7','=D7/B7']];
summary.getRange('C8:F8').formulas=[[`=SUMIFS(K${start}:K${end},B${start}:B${end},A8)`,`=SUMIFS(L${start}:L${end},B${start}:B${end},A8)`,'=C8/B8','=D8/B8']];
summary.getRange('E6:F8').setNumberFormat('0.0%');
summary.getRange('A5:F5').format={fill:'#E8EEF4',font:{bold:true},wrapText:true,rowHeight:32};
summary.getRange('A9').values=[['N：限定问题内未发现有支持的风险；R：需法律复核；U：决定性信息不足；FAIL：技术/校验失败。']];
summary.getRange('A10').values=[['语义标签仅供诊断：不得把被阻断输出计作成功交付。机器推定范围不是人工批准。']];
table(summary,12,data.comparison_headers,data.comparison_rows,'PairedGateReview',[16,13,15,17,18,16,33,15,28,62,15,15,18,28,45]);
summary.getRange(`A${start}:O${end}`).format.rowHeight=90;
summary.getRange(`D${start}:D${end}`).conditionalFormats.add('containsText',{text:'FAIL',format:{fill:'#FBE2E2',font:{color:'#A42020'}}});
summary.getRange(`H${start}:H${end}`).conditionalFormats.add('containsText',{text:'是',format:{fill:'#FFF0CB'}});
summary.getRange(`N${start}:O${end}`).format.fill='#FFF4D6';
summary.getRange(`N${start}:N${end}`).dataValidation={rule:{type:'list',values:['边界认可','需澄清原问题','需修正机器范围']}};

setup(handoff,24,compact.length+5);
handoff.getRange('A2').values=[['审查交接明细']];handoff.getRange('A2').format.font={name:'Arial',size:14,bold:true};
handoff.getRange('A3').values=[['长文本按字段完整分段至“证据全文”；模型解释未经核验，不能作为独立法律依据。人工决定列留空。']];
table(handoff,5,data.handoff_headers,compact,'ReviewHandoff',[16,18,48,40,25,48,48,48,20,38,32,24,40,26,50,32,50,50,50,50,50,50,24,28]);
handoff.getRangeByIndexes(5,0,compact.length,24).format.rowHeight=154;
handoff.getRangeByIndexes(5,11,compact.length,2).format.fill='#FFF4D6';
handoff.getRangeByIndexes(5,23,compact.length,1).format.fill='#FFF4D6';
handoff.getRangeByIndexes(5,13,compact.length,1).conditionalFormats.add('containsText',{text:'blocked',format:{fill:'#FBE2E2',font:{color:'#A42020'}}});

setup(evidence,4,segments.length+5);
evidence.getRange('A2').values=[['证据全文与解释原文']];evidence.getRange('A2').format.font={name:'Arial',size:14,bold:true};
evidence.getRange('A3').values=[['按单元、字段筛选，依序号拼接即可恢复完整文本；未改写、未删除内容。']];
evidence.getRange('A4').values=[['来源：固定响应回放JSON；原始输入和响应哈希见回放manifest，冻结阶段A参照对应见独立analysis文件。']];
table(evidence,5,['单元','字段','段序号','完整分段文本'],segments,'EvidenceText',[17,43,13,110]);
evidence.getRangeByIndexes(5,0,segments.length,4).format.rowHeight=92;
evidence.getRangeByIndexes(5,2,segments.length,1).setNumberFormat('0');

// Verify segmentation independently before export.
for (const row of data.handoff_rows) for (let j=0;j<row.length;j++) {
  const value=row[j]; if (typeof value!=='string'||value.length<=180) continue;
  const restored=segments.filter(s=>s[0]===row[0]&&s[1]===data.handoff_headers[j]).map(s=>s[3]).join('');
  if (restored!==value) throw new Error('Evidence text reconstruction failed');
}
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'结果对照!A5:F8',include:'values,formulas',tableMaxRows:4,tableMaxCols:6,maxChars:2200})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:10},maxChars:1500})).ndjson);
for (const [sheetName,range,file] of [['结果对照','A2:F8','summary'],['审查交接','A5:D7','handoff'],['证据全文','A5:D8','evidence']]) {
  const png=await wb.render({sheetName,range,scale:1,format:'png'});
  await fs.writeFile(path.join(outputDir,file+'.png'),new Uint8Array(await png.arrayBuffer()));
}
const file=await SpreadsheetFile.exportXlsx(wb);
await file.save(path.join(outputDir,'TaskGate_v2_45条离线复核.xlsx'));
await fs.writeFile(path.join(outputDir,'export_checks.json'),JSON.stringify({records:data.comparison_rows.length,handoff_rows:compact.length,segments:segments.length,lossless_text_reconstruction:true},null,2));
console.log(JSON.stringify({output:path.join(outputDir,'TaskGate_v2_45条离线复核.xlsx'),records:compact.length}));
