import type { Category } from '../api';

export const REPORT_MODES = ['服務性問題', '額外要求', '申訴處理', '人身安全事件'] as const;
export type ReportMode = typeof REPORT_MODES[number];
export interface Scenario { id: string; text: string; sources: SourceId[] }
export const SCENARIO_SOURCES = {
  H: { title: '衛福部《居家服務督導員工作手冊》', locator: '第二章服務計畫、意見反映與申訴；第四章風險管理', url: 'https://www.mohw.gov.tw/dl-100619-d08f6862-e9f4-48be-99cb-a79d0bb0b2f9.html' },
  E: { title: '臺南市114年度居家式長照機構評鑑基準', locator: 'B3–B5照顧計畫與服務品質、B8緊急事件、D1–D3契約收費申訴；作設計參考，非嘉安適用性認定', url: 'https://sab.tainan.gov.tw/News_Content.aspx?n=21215&s=8715379' },
  C: { title: '衛福部居家式服務類定型化契約範本', locator: '第3條服務項目、第6條費用及申訴與隱私相關條款', url: 'https://www.mohw.gov.tw/dl-87923-c9451cbc-7da0-4f5c-b877-6a721844bc3c.html' },
  R: { title: '鄭婷之（2023）居家服務督導落實督導功能的經驗與困境之研究', locator: '第四章：契約外期待、服務關係界線；PDF第88–100頁', url: 'https://ir.lib.cyut.edu.tw/bitstream/310901800/42448/1/111CYUT0201009-002.pdf' },
  L: { title: '柯欣妮（2023）我國居家照顧服務員之情緒勞動探討', locator: 'PDF第66頁：額外工作與情緒壓力；質性研究，不是機構規範', url: 'https://ah.lib.nccu.edu.tw/bitstream/140.119/147090/1/201801.pdf' },
} as const;
export type SourceId = keyof typeof SCENARIO_SOURCES;

// Service catalogue stays in reportServices.ts. These are reporting prompts,
// synthesized from service-plan/quality/risk principles, never treatment instructions.
export const SERVICE_GROUPS = {
  hygiene: { codes: ['BA01','BA02','BA07','BA08','BA23','BA24'], reasons: ['個案不願接受此項清潔或日常照顧', '用品或環境準備不足，需協調', '照顧需求改變，需確認服務內容'] },
  measurement: { codes: ['BA03'], reasons: ['測量設備無法正常使用', '個案不願接受測量', '測量紀錄或服務指示需督導確認'] },
  nutrition: { codes: ['BA04','BA05'], reasons: ['餐食或進食需求需重新確認', '備餐或進食用品準備不足', '本項服務內容與照顧計畫不一致'] },
  mobility: { codes: ['BA10','BA11','BA12'], reasons: ['活動環境或輔具準備不足', '個案不願接受本項活動協助', '現場人力或安全條件需督導確認'] },
  outing: { codes: ['BA13','BA14'], reasons: ['外出路線或交通安排需協調', '行程時間與原服務計畫不一致', '陪同所需文件或用品尚未備齊'] },
  housekeeping: { codes: ['BA15'], reasons: ['家務範圍或使用空間需確認', '清潔用品或環境影響本項服務', '個案與家屬對本項服務內容理解不同'] },
  errands: { codes: ['BA16'], reasons: ['代購清單或交付內容不清楚', '購買對象或費用紀錄需核對', '取送行程或交付安排有困難'] },
  assistance: { codes: ['BA17'], reasons: ['服務計畫或指示內容不清楚', '現場用品或安全條件不足', '個案對此項協助有疑慮'] },
  support: { codes: ['BA18','BA20','BA22','GA09','SC09'], reasons: ['本項服務的時段或交接安排需協調', '照顧狀況改變，需重新確認', '現場照顧交接資訊不足'] },
} as const;
const EXTRA: Scenario[] = [
  { id:'extra-increase', text:'要求增加服務項目或次數', sources:['H','C'] },
  { id:'extra-time', text:'要求更改時段或延長服務時間', sources:['H','C'] },
  { id:'extra-outside', text:'要求執行原核定或約定以外的工作', sources:['H','C','R'] },
  { id:'extra-family', text:'家屬要求照顧其他人或處理其他家務', sources:['R','L','C'] },
  { id:'extra-private', text:'要求下班後或私下另做服務', sources:['R','C'] },
];
// The four quick-classification incident types themselves ARE the reason
// text (no separate BA sub-reason list), per 10/30 嘉安訪談第六輪 requirement.
// Emergency marking (optional, confirmed separately in ReportPreviewPage)
// maps each type to the existing jiaan1030 emergency category codes; there is
// no dedicated backend category for sexual harassment, so it is mapped to
// 'other' — confirmed with user, not invented.
const SAFETY_EVENT: Scenario[] = [
  { id:'safety-sexual', text:'性騷擾／不當觸碰', sources:['H','E'] },
  { id:'safety-violence', text:'暴力／人身安全', sources:['H','E'] },
  { id:'safety-fall', text:'跌倒', sources:['H','E'] },
  { id:'safety-injury', text:'傷口／異常狀況', sources:['H','E'] },
];
export const SAFETY_EMERGENCY_CATEGORY: Record<string, 'violence'|'fall'|'injury'|'other'> = {
  '性騷擾／不當觸碰':'other',
  '暴力／人身安全':'violence',
  '跌倒':'fall',
  '傷口／異常狀況':'injury',
};
const COMPLAINT: Scenario[] = [
  { id:'complaint-quality', text:'反映服務品質或未依計畫執行', sources:['H','E'] },
  { id:'complaint-time', text:'反映遲到、早退、缺席或服務時間爭議', sources:['H','E'] },
  { id:'complaint-communication', text:'反映溝通、態度或變更未告知', sources:['H','R'] },
  { id:'complaint-fees', text:'反映收費、收據或自費說明爭議', sources:['H','E','C'] },
  { id:'complaint-privacy', text:'反映個資、隱私或尊嚴未受尊重', sources:['H','E','C'] },
  { id:'complaint-conduct', text:'反映不當言行、疑似侵害或越權行為', sources:['H','R'] },
];
export function getReportScenarios(mode: ReportMode | null, code?: string): Scenario[] {
  if(mode==='額外要求') return EXTRA;
  if(mode==='申訴處理') return COMPLAINT;
  if(mode==='人身安全事件') return SAFETY_EVENT;
  if(mode!=='服務性問題' || !code) return [];
  const group=Object.values(SERVICE_GROUPS).find(g=>(g.codes as readonly string[]).includes(code));
  return group ? group.reasons.map((text,i)=>({id:`service-${code}-${i+1}`,text,sources:code==='BA16'?['H','C']:['H','E']})) : [];
}

// Only exact, existing API categories are eligible; never invent UUIDs or choose
// the first returned category. Complaint -> Other was explicitly authorized by user.
export const RECEIVING_CATEGORIES: Record<ReportMode, readonly string[]> = {
  '服務性問題':['服務範圍'],
  '額外要求':['額外要求','家屬額外要求'],
  '申訴處理':['申訴處理','申訴','其他'],
  '人身安全事件':['事件處理規範'],
};
export function resolveReceivingCategory(mode: ReportMode | null, categories: Category[] | null): Category | null {
  if(!mode || !categories) return null;
  for(const name of RECEIVING_CATEGORIES[mode]) {
    const matches=categories.filter(c=>c.name===name);
    if(matches.length>1) return null;
    if(matches.length===1) return matches[0];
  }
  return null;
}
