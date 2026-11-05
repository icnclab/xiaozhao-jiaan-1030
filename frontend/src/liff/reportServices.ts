/** Names transcribed from the service table supplied by the user. No billing rules or case mapping. */
export interface ReportService {
  code: string;
  name: string;
  options?: { code: string; name: string }[];
}

export const REPORT_SERVICES: ReportService[] = [
  { code: 'BA01', name: '基本身體清潔' },
  { code: 'BA02', name: '基本日常照顧(30)' },
  { code: 'BA03', name: '測量生命徵象' },
  { code: 'BA04', name: '協助進食或管灌餵食' },
  { code: 'BA05', name: '餐食照顧' },
  { code: 'BA07', name: '協助沐浴及洗頭' },
  { code: 'BA08', name: '足部照護' },
  { code: 'BA10', name: '翻身拍背' },
  { code: 'BA11', name: '肢體關節活動' },
  { code: 'BA12', name: '協助上(下)樓梯' },
  { code: 'BA13', name: '陪同外出(30)' },
  { code: 'BA14', name: '陪同就醫(90)' },
  { code: 'BA15', name: '家務協助', options: [{ code: 'self', name: '自用' }, { code: 'shared', name: '共用' }] },
  { code: 'BA16', name: '代購或代領代送服務', options: [{ code: 'self', name: '自用' }, { code: 'shared', name: '共用' }] },
  { code: 'BA17', name: '協助執行輔助性醫療', options: [
    { code: 'a', name: '管路內分泌物抽取' },
    { code: 'b', name: '口鼻抽吸' },
    { code: 'c', name: '管路清潔' },
    { code: 'd1', name: '血糖機檢驗血糖' },
    { code: 'd2', name: '甘油球通便' },
    { code: 'e', name: '依指示入藥盒' },
  ] },
  { code: 'BA18', name: '安全看視(30)' },
  { code: 'BA20', name: '陪伴服務(30)' },
  { code: 'BA22', name: '巡視服務(至少3次)' },
  { code: 'BA23', name: '協助洗頭' },
  { code: 'BA24', name: '協助排泄' },
  { code: 'GA09', name: '居家喘息服務(2小時/次)' },
  { code: 'SC09', name: '短照服務(2小時/次)' },
];
