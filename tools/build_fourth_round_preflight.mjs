import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/icncl/Downloads/32 份知識庫官方來源核對表.xlsx";
const outputPath = "docs/知識庫32筆官方來源預檢結果.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const source = workbook.worksheets.getItem("官方連結待填");
const raw = source.getRange("A5:J36").values;

const exact = new Set([1, 2, 7, 9, 10, 11, 12, 13, 14, 17, 18, 19, 20, 21, 23, 24]);
const mohwTimeout = new Set([3, 4, 5, 6, 8, 16]);
const dateNeedsReview = new Set([15, 22, 25, 26, 27, 28, 29, 30, 31, 32]);
const cleanUrl = (value) => String(value ?? "").trim().replace(/[。．]+$/u, "");

const rows = raw.map((r) => {
  const n = Number(r[0]);
  let site, match, attachment, recommendation, todo;
  if (exact.has(n)) {
    site = "官方頁可達，名稱／法規代碼與預期網域相符";
    match = "名稱與顯示日期相符";
    attachment = [17,18,19,20,21].includes(n) ? "不適用（法規全文頁）" : "官方頁已列出同名附件";
    recommendation = "可送人工核准";
    todo = "由有權人員複核保存檔 SHA／內容後決定；本預檢不核准";
  } else if (mohwTimeout.has(n)) {
    site = "1966 官方彙整頁可確認標題與目標連結；衛福部函釋頁逾時";
    match = "標題／函號可由官方彙整頁交叉確認，正文未完整抓取";
    attachment = "函釋目標頁需人工開啟確認正文";
    recommendation = "需人工補充資料";
    todo = "人工開啟 mohwlaw 目標頁，核對發文日、函號與全文；保留連線逾時證據";
  } else {
    site = "官方頁可達，主法規／評鑑頁與預期網域相符";
    match = "頁面標題或附件存在；顯示日期可能是未來生效日而非修正日";
    attachment = "官方頁列出對應附件或上層資料集";
    recommendation = "需人工補充資料";
    todo = dateNeedsReview.has(n) ? "人工確認顯示日期欄係修正日、公告日或生效日，並核對實際附件版本" : "人工複核附件版本";
  }
  if (n === 16) todo = "已清除 URL 末尾全形句號；人工開啟函釋頁核對發文日、函號與正文；原 URL 留存於本表";
  return [n, r[1], r[5], cleanUrl(r[5]), "已對應正式 32 版本之一（已發布不等於官方來源核准）",
    site, match, attachment, recommendation, "待核准（實際核准數 0）", todo, r[6], r[2], r[4]];
});

const result = workbook.worksheets.add("預檢結果");
result.getRange("A1:N1").merge();
result.getRange("A1").values = [["小照知識庫 32 筆官方來源預檢結果"]];
result.getRange("A2:N2").merge();
result.getRange("A2").values = [["預檢日期：2026-11-12｜只做唯讀核對，不代表核准、發布或寫入正式資料庫"]];
result.getRange("A3:D3").values = [["總筆數", 32, "實際核准數", 0]];
result.getRange("E3:H3").values = [["可送人工核准", `=COUNTIF(I6:I37,"可送人工核准")`, "需人工補充資料", `=COUNTIF(I6:I37,"需人工補充資料")`]];
result.getRange("I3:J3").values = [["驗證不通過", `=COUNTIF(I6:I37,"驗證不通過")`]];
result.getRange("A5:N5").values = [["編號","文件名稱","原始 URL","清理後 URL","正式 DB 比對","網站驗證","文件／日期核對","附件存在","建議狀態","實際核准狀態","錯誤／人工待辦","原始檔名","文件類型","原顯示日期"]];
result.getRange("A6:N37").values = rows;
result.freezePanes.freezeRows(5);
result.getRange("A1:N37").format.font = { name: "Microsoft JhengHei", size: 10 };
result.getRange("A1:N1").format = { fill: "#1F4E78", font: { name: "Microsoft JhengHei", size: 16, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
result.getRange("A2:N2").format = { fill: "#D9EAF7", font: { name: "Microsoft JhengHei", italic: true, color: "#1F2937" } };
result.getRange("A3:J3").format = { fill: "#E2F0D9", font: { name: "Microsoft JhengHei", bold: true } };
result.getRange("A5:N5").format = { fill: "#4472C4", font: { name: "Microsoft JhengHei", bold: true, color: "#FFFFFF" }, wrapText: true, horizontalAlignment: "center" };
result.getRange("A6:N37").format.wrapText = true;
result.getRange("A6:A37").format.horizontalAlignment = "center";
for (const [col, width] of Object.entries({A:7,B:34,C:44,D:44,E:28,F:38,G:34,H:28,I:18,J:20,K:42,L:38,M:14,N:14})) result.getRange(`${col}:${col}`).format.columnWidth = width;
result.getRange("6:37").format.rowHeight = 56;
result.getRange("I6:I37").conditionalFormats.addCustom('=I6="可送人工核准"', { fill: "#E2F0D9", font: { color: "#215E21", bold: true } });
result.getRange("I6:I37").conditionalFormats.addCustom('=I6="需人工補充資料"', { fill: "#FFF2CC", font: { color: "#7F6000", bold: true } });

const pdf = workbook.worksheets.add("6份候選PDF");
pdf.getRange("A1:J1").merge(); pdf.getRange("A1").values = [["6 份新增候選 PDF 唯讀檢查"]];
pdf.getRange("A3:J3").values = [["文件名稱","SHA-256","頁數","檔案大小(Bytes)","文件日期／函號","官方附件存在","正式 DB SHA 重複","內容關係","建議動作","核准狀態"]];
pdf.getRange("A4:J9").values = [
  ["長照專業服務手冊1120109(公告修正).pdf","7fed0e00e5ee35819b90b2e8201220c85fa8b7e30f4d99f7da8d371d8ce45537",17,13545060,"112-01-09 修正版（掃描影像，文字抽取為空）","是","否","與既有『長照專業服務手冊.pdf』高度重疊，須做版本差異","建立候選新版本；人工比對後再決定，禁止覆蓋","待人工審核"],
  ["長照專業服務手冊-修正說明表(公告).pdf","687f69acd1b77f9af9355b4e8a2ac98e807c4f803e4641458b45f12dd97b1769",24,924803,"112-01-09","是","否","手冊修正說明附件","建議新增為關聯文件／附件，人工核准後發布","待人工審核"],
  ["長期照顧專業課程(LevelⅡ)及整合課程(LevelⅢ)授課講師資格.pdf","ec1a9944446836313e72e14e2f3e3cba847e46ef28fa023971c98c551267d188",1,258154,"110-02-25 衛部顧字第1091963201號","是","否","新主題文件","建議新增草稿，人工核准後發布","待人工審核"],
  ["長期照顧專業課程(LevelⅡ).pdf","36f5e469ce64acc2399d42f85d7514ce943715411a1dcb434b9a29968b5de70e",79,4619314,"110-02-25 衛部顧字第1091963201號","是","否","新主題文件","建議新增草稿，人工核准後發布","待人工審核"],
  ["長期照顧整合課程(LevelⅢ).pdf","01375efdb1af30f0ad1d36b868386e40d511526d1dd9c9cf8480cf1b116e5a20",1,252793,"110-02-25 衛部顧字第1091963201號","是","否","新主題文件","建議新增草稿，人工核准後發布","待人工審核"],
  ["L2+L3課程及師資公告函.pdf","c519d5f0ba0044e63e4ee936f7d9ec0f7dcfc043da4da4871c17c76dd2b97241",2,83943,"110-02-25 衛部顧字第1091963201號","是","否","上述課程與師資之公告函","建議新增關聯公告函，人工核准後發布","待人工審核"],
];
pdf.getRange("A11:J11").merge(); pdf.getRange("A11").values = [["共同官方來源：https://1966.gov.tw/LTC/cp-6451-70123-207.html；本表只提供匯入建議，未寫入 DB／RAG。"]];
pdf.getRange("A1:J11").format.font = { name: "Microsoft JhengHei", size: 10 };
pdf.getRange("A1:J1").format = { fill: "#1F4E78", font: { name: "Microsoft JhengHei", size: 15, bold: true, color: "#FFFFFF" } };
pdf.getRange("A3:J3").format = { fill: "#4472C4", font: { name: "Microsoft JhengHei", bold: true, color: "#FFFFFF" }, wrapText: true };
pdf.getRange("A4:J11").format.wrapText = true; pdf.freezePanes.freezeRows(3);
for (const [col,width] of Object.entries({A:48,B:66,C:8,D:16,E:34,F:16,G:18,H:34,I:38,J:18})) pdf.getRange(`${col}:${col}`).format.columnWidth = width;
pdf.getRange("4:9").format.rowHeight = 58;

const extra = workbook.worksheets.add("4筆追加候選");
extra.getRange("A1:H1").merge(); extra.getRange("A1").values = [["4 筆追加官方候選預檢（未下載正文、未發布）"]];
extra.getRange("A3:H3").values = [["代號","URL","官方網域","頁面驗證","文件／日期","與長照 RAG 關聯","建議","狀態"]];
extra.getRange("A4:H7").values = [
  ["A","https://mohwlaw.mohw.gov.tw/FINT/FINTQRY04.aspx?starDate=00000000&endDate=99991231&no=&n1=&n2=1110115241&kt=&kw=&kw2=&kw3=&kw4=&valid=3&type=etype_&RowNo=1","mohwlaw.mohw.gov.tw","官方系統逾時，未取得正文","待人工核對函號／日期／標題","可能相關，證據不足","人工開頁保存正文與證據後再評估","需人工補充資料"],
  ["B","https://mohwlaw.mohw.gov.tw/FINT/FINTQRY04.aspx?starDate=00000000&endDate=99991231&no=&n1=&n2=1131963359&kt=&kw=&kw2=&kw3=&kw4=&valid=3&type=etype_&RowNo=1","mohwlaw.mohw.gov.tw","官方系統逾時，未取得正文","待人工核對函號／日期／標題","可能相關，證據不足","人工開頁保存正文與證據後再評估","需人工補充資料"],
  ["C","https://mohwlaw.mohw.gov.tw/FINT/FINTQRY04.aspx?starDate=00000000&endDate=99991231&no=&n1=&n2=1130156711&kt=&kw=&kw2=&kw3=&kw4=&valid=3&type=etype_&RowNo=1","mohwlaw.mohw.gov.tw","官方系統逾時，未取得正文","待人工核對函號／日期／標題","可能相關，證據不足","人工開頁保存正文與證據後再評估","需人工補充資料"],
  ["D","https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=C0000001","law.moj.gov.tw","可達；中華民國刑法，修正日 115-07-22","名稱／日期可確認","範圍過廣，非長照專屬文件","不要整部直接納入；先由治理人員界定必要條文與用途","需人工補充資料"],
];
extra.getRange("A1:H7").format.font = { name: "Microsoft JhengHei", size: 10 }; extra.getRange("A1:H1").format = { fill: "#1F4E78", font: { name: "Microsoft JhengHei", size: 15, bold: true, color: "#FFFFFF" } };
extra.getRange("A3:H3").format = { fill: "#4472C4", font: { name: "Microsoft JhengHei", bold: true, color: "#FFFFFF" }, wrapText: true };
extra.getRange("A4:H7").format.wrapText = true; extra.freezePanes.freezeRows(3);
for (const [col,width] of Object.entries({A:8,B:70,C:24,D:34,E:28,F:32,G:40,H:20})) extra.getRange(`${col}:${col}`).format.columnWidth = width;
extra.getRange("4:7").format.rowHeight = 62;

workbook.recalculate();
const checks = await workbook.inspect({ kind: "table", range: "預檢結果!A1:N12", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 14 });
console.log(checks.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log(errors.ndjson);
const preview = await workbook.render({ sheetName: "預檢結果", range: "A1:N12", scale: 1, format: "png" });
await fs.mkdir("tmp/fourth_round_workbook", { recursive: true });
await fs.writeFile("tmp/fourth_round_workbook/preflight-preview.png", new Uint8Array(await preview.arrayBuffer()));
await fs.mkdir("docs", { recursive: true });
await (await SpreadsheetFile.exportXlsx(workbook)).save(outputPath);
console.log(`SAVED ${outputPath}`);
