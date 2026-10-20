import fs from 'node:fs/promises';
import { Workbook } from '@oai/artifact-tool';

const directory = new URL('.', import.meta.url);
const { records } = JSON.parse(await fs.readFile(new URL('qa_history_sources.json', directory), 'utf8'));
const sourceOverrides = {
  T03: '居家服務督導員工作手冊／第四章 風險管理：事件嚴重度與通報時效、初報／續報／結報及紀錄',
  T04: '長照專業服務操作指引／附錄一 服務紀錄參考格式',
  T05: '附件一－115年度居家式長期照顧服務機構評鑑基準／A2 工作手冊之制定與執行情形',
  T09: '長期照顧服務人員訓練認證繼續教育及登錄辦法（本題只要求法規名稱）',
};
const headers = ['題號', '正式題庫序號', '來源類型', '問題', '正確來源', '系統回答秒數（後端歷史）',
  '人工查找秒數', '是否找到正確來源', '是否答案正確', '人工找到的來源／段落', '備註'];
const rows = records.map(r => [r.id, r.formal_index, r.category, r.question,
  sourceOverrides[r.id] ?? r.correct_source, r.system_seconds, null, null, null, null, null]);
if (rows.length !== 10 || new Set(rows.map(r => r[0])).size !== 10) throw new Error('Expected 10 unique questions');
const workbook = Workbook.create();
const sheet = workbook.worksheets.add('查找時間紀錄');
sheet.getRange('A1:K11').values = [headers, ...rows];
sheet.getRange('A1:K11').format.wrapText = true;
sheet.getRange('A1:K11').format.rowHeight = 65;
sheet.getRange('A1:K1').format.rowHeight = 32;
sheet.getRange('A1:K1').format.fill = '#E8EEF4';
sheet.getRange('A1:K1').format.font.bold = true;
sheet.getRange('A:A').format.columnWidth = 8;
sheet.getRange('B:C').format.columnWidth = 16;
sheet.getRange('D:E').format.columnWidth = 70;
sheet.getRange('F:K').format.columnWidth = 22;
sheet.getRange('F2:G11').setNumberFormat('0.000');
sheet.freezePanes.freezeRows(1);
workbook.recalculate();
const values = sheet.getRange('A1:K11').values;
for (let i = 1; i <= 10; i++) {
  if (typeof values[i][5] !== 'number' || !(values[i][5] > 0)) throw new Error('Historical timing missing');
  if (values[i].slice(6).some(v => v != null && v !== '')) throw new Error('Human observation must be blank');
}
console.log((await workbook.inspect({kind:'table', range:'查找時間紀錄!A1:D11',
  include:'values', tableMaxRows:11, tableMaxCols:4, maxChars:1500})).ndjson);
const escape = v => `"${String(v ?? '').replaceAll('"', '""')}"`;
await fs.writeFile(new URL('查找時間比較_10題.csv', directory), '\ufeff' + values.map(row => row.map(escape).join(',')).join('\r\n') + '\r\n', 'utf8');
const preview = await workbook.render({sheetName:'查找時間紀錄', range:'A1:D11', scale:1, format:'png'});
await fs.writeFile(new URL('preview.png', directory), new Uint8Array(await preview.arrayBuffer()));
const questions = '# 小照人工查找實驗：受測題目\n\n受測者代號：________　日期：________　法規查找熟悉程度：________\n\n' +
  '請使用實驗提供的 32 份 MD。可用檔名、目錄、Ctrl+F 與一般文字搜尋；不可使用小照或其他 AI。每題找到能回答問題的原文後，指出文件與段落，並簡述答案。\n\n' +
  records.map(r => `## ${r.id}\n\n${r.question}\n\n人工查找秒數：________\n\n找到的文件／段落：________\n\n簡述答案：________\n\n`).join('');
await fs.writeFile(new URL('受測題目單.md', directory), questions, 'utf8');
console.log('CSV and participant questions saved.');
