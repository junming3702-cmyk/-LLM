// Presentation adapter only. All legal states arrive from the Python gate.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const [packetPath, outputDir, runtimeDir] = process.argv.slice(2);
if (!packetPath || !outputDir || !runtimeDir) throw new Error('packet/output/runtime required');
const requireRuntime = createRequire(path.join(runtimeDir, 'package.json'));
const { Workbook, SpreadsheetFile, FileBlob } = await import(pathToFileURL(requireRuntime.resolve('@oai/artifact-tool')));
const packet = JSON.parse(await fs.readFile(packetPath, 'utf8'));
if (packet.export_version !== 'three-layer-xlsx-v1' || packet.sheets.length !== 4 ||
    packet.legal_accuracy !== null || packet.expert_agreement !== null || packet.joint_handoff_effectiveness !== null)
  throw new Error('unsupported_packet');
const finalPath = path.join(outputDir, '三层协议_离线复核.xlsx');
try { await fs.access(finalPath); throw new Error('refuse_overwrite'); }
catch (e) { if (e.code !== 'ENOENT') throw e; }
const wb = Workbook.create();
const headerRow = 6;
const checks = [];
// Artifact Tool interprets leading '=' in .values; its documented escape is
// stripped on export. Other leading characters already remain typed strings.
// Do not add visible apostrophes to '@', '+', '-' or tab-prefixed source text.
const literal = value => typeof value === 'string' && value.startsWith('=') ? "'" + value : value;
const colName = n => { let s = ''; for (n++; n; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + (n - 1) % 26) + s; return s; };
for (const [idx, source] of packet.sheets.entries()) {
  const sheet = wb.worksheets.add(source.name);
  const end = headerRow + Math.max(source.rows.length, 1);
  const last = colName(source.columns.length - 1);
  sheet.showGridLines = false;
  sheet.getRange(`A1:${last}${end}`).format.font = { name: 'Arial', size: 11, color: '#172536' };
  sheet.getRange(`A1:${last}${end}`).format.verticalAlignment = 'center';
  sheet.getRange('A2').values = [[source.name + '（候选协议）']];
  sheet.getRange('A2').format.font = { name: 'Arial', size: 15, bold: true };
  sheet.getRange('A3').values = [[packet.boundary]];
  sheet.getRange('A4').values = [[source.note]];
  sheet.getRange('A3:A4').format.font = { name: 'Arial', size: 11, color: '#526070' };
  sheet.getRange(`A6:${last}6`).values = [source.columns];
  sheet.getRange(`A6:${last}6`).format = { fill: '#253D56', font: { name: 'Arial', size: 11, bold: true, color: '#FFFFFF' },
    wrapText: true, rowHeight: 35, horizontalAlignment: 'center', verticalAlignment: 'center' };
  if (source.rows.length) {
    sheet.getRangeByIndexes(6, 0, source.rows.length, source.columns.length).values = source.rows.map(r => r.map(literal));
    const body = sheet.getRange(`A7:${last}${end}`);
    body.format.wrapText = true;
    body.format.verticalAlignment = 'top';
    body.format.rowHeight = 94;
    const t = sheet.tables.add(`A6:${last}${end}`, true, `ProtocolTable${idx+1}`);
    t.showFilterButton = true;
  }
  for (let i = 0; i < source.widths.length; i++) sheet.getRange(`${colName(i)}1:${colName(i)}${end}`).format.columnWidth = source.widths[i];
  // Height follows bounded line estimates. Never truncate cell content.
  for (let i = 0; i < source.rows.length; i++) {
    const lines = Math.max(...source.rows[i].map((v, j) => typeof v === 'string'
      ? v.split('\n').reduce((n, part) => n + Math.max(1, Math.ceil([...part].reduce((k, c) => k + (c.charCodeAt(0)>255?2:1),0) / (source.widths[j]-2))), 0) : 1));
    sheet.getRange(`A${i+7}:${last}${i+7}`).format.rowHeight = Math.min(409, Math.max(68, lines * 16 + 14));
  }
  if (source.rows.length && idx === 0) {
    sheet.getRange(`M7:N${end}`).format.fill = '#FFF4D5';
    sheet.getRange(`D7:D${end}`).conditionalFormats.add('containsText', { text: 'blocked_by_decisive_gap', format: { fill: '#FCE8E6', font: { color: '#922B21' } } });
    sheet.getRange(`G7:G${end}`).conditionalFormats.add('containsText', { text: 'needs_', format: { fill: '#FFF0D2', font: { color: '#714D00' } } });
  }
  sheet.freezePanes.freezeRows(6);
  sheet.freezePanes.freezeColumns(2);
}
wb.recalculate();
const errorScan = await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 30 }, maxChars: 2500 });
await fs.writeFile(path.join(outputDir, 'formula_error_scan.ndjson'), errorScan.ndjson);
// Render every sheet, with additional right-side detail for the wide audit tables.
for (const [idx, source] of packet.sheets.entries()) {
  const sheet = wb.worksheets.getItem(source.name);
  const end = 6 + source.rows.length;
  const grid = sheet.getRangeByIndexes(6, 0, Math.max(1, source.rows.length), source.columns.length);
  const formulas = grid.formulas;
  if (formulas.some(row => row.some(v => !!v))) throw new Error('unexpected_formula_in_source_cells');
  const inspected = await wb.inspect({ kind: 'table', range: `${source.name}!A6:G${Math.min(10, end)}`, include: 'values,formulas', tableMaxRows: 5, tableMaxCols: 7, maxChars: 3000 });
  await fs.writeFile(path.join(outputDir, `inspect_${idx+1}.ndjson`), inspected.ndjson);
  const renders = [`A2:G${Math.min(10, Math.max(7,end))}`, `H6:${colName(source.columns.length-1)}${Math.min(9,Math.max(7,end))}`];
  for (const [part, range] of renders.entries()) {
    const blob = await wb.render({ sheetName: source.name, range, scale: 1.4, format: 'png' });
    await fs.writeFile(path.join(outputDir, `preview_${idx+1}_${part+1}.png`), new Uint8Array(await blob.arrayBuffer()));
  }
}
const file = await SpreadsheetFile.exportXlsx(wb);
await file.save(finalPath);
const saved = await SpreadsheetFile.importXlsx(await FileBlob.load(finalPath));
for (const source of packet.sheets) {
  const s = saved.worksheets.getItem(source.name);
  const expected = [source.columns, ...source.rows];
  const actual = s.getRangeByIndexes(5, 0, expected.length, source.columns.length).values;
  if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(`readback_value_mismatch:${source.name}`);
  if (s.getRangeByIndexes(5, 0, expected.length, source.columns.length).formulas.some(r => r.some(Boolean)))
    throw new Error('readback_unexpected_formula');
  checks.push({sheet:source.name, rows:source.rows.length, columns:source.columns.length, exact_cell_readback:true, formula_cells:0});
}
await fs.writeFile(path.join(outputDir, 'xlsx_checks.json'), JSON.stringify({export_version:packet.export_version, checks,
  sources_unchanged:true, human_review_required:true, legal_metrics_computed:false, all_sheets_rendered:true}, null, 2)+'\n');
console.log(JSON.stringify({status:'passed', sheets:checks.length, exported:finalPath}));
