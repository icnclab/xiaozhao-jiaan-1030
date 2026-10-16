import { useEffect, useState } from "react";
import { api } from "../../api";
import { useLiff } from "../LiffApp";
import { ErrorBox } from "../components";

interface Coverage {
  updated_at: string | null;
  documents: { title: string; doc_type: string; scope: string; version_label: string; effective_from: string | null; effective_to: string | null; source: string | null }[];
  not_covered: string[];
}

const TYPE_LABELS: Record<string, string> = { regulation: "法規", internal_rule: "機構內規", sop: "作業程序", other: "其他" };

export function HelpPage() {
  const { config } = useLiff();
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    api<Coverage>("/api/documents/coverage").then(setCoverage).catch(setError);
  }, []);
  return (
    <div className="page stack">
      <h1>使用說明</h1>
      <div className="card stack">
        <h3>怎麼問</h3>
        <p>文字輸入，或說「<strong>{config.wake_words[0]}</strong>，家屬要我代購成藥可以嗎？」。也可以在 LINE 聊天室直接傳文字或語音訊息。</p>
        <p>請用「住民」「家屬」代稱，不要說姓名、房號或身分證字號。系統會遮罩常見個資樣式，但無法保證全部遮到。</p>
        <h3>小照會做什麼</h3>
        <p>只回答知識庫裡有依據的規範問題，每句附出處（文件名、條號或頁碼、版本、生效日）。依據不足、文件互相衝突、涉及醫療判斷、用藥或補助金額時，會轉督導確認，不會自己猜。</p>
        <p>回答是「AI 初步參考」，不是最終決定；有疑慮請按「送交督導確認」。</p>
        <h3>錄音</h3>
        <p>談話錄音前請告知在場的人並取得同意。原始錄音轉成文字後立即刪除；未確認的逐字稿最多暫存 24 小時。</p>
      </div>
      <div className="card stack">
        <h3>知識庫涵蓋範圍</h3>
        <ErrorBox error={error} />
        <p className="muted small">最近更新：{coverage?.updated_at ? new Date(coverage.updated_at).toLocaleString("zh-TW") : "—"}</p>
        {coverage?.documents.map((d) => (
          <div key={d.title + d.version_label} className="small">
            <span className="tag">{TYPE_LABELS[d.doc_type] ?? d.doc_type}</span> {d.title}｜{d.version_label}｜{d.effective_from ?? "未填"} 生效
          </div>
        ))}
        <h3>不涵蓋</h3>
        <ul className="small">{coverage?.not_covered.map((x) => <li key={x}>{x}</li>)}</ul>
      </div>
      <div className="card small muted">
        <p>資料流說明：LINE 聊天室的文字與語音會經 LINE 平臺傳遞；免手模式的喚醒詞辨識使用瀏覽器內建語音服務。正式提問內容由本系統處理。詳見 docs/data-flow.md。</p>
        <p>目前模式：{Object.entries(config.modes).map(([k, v]) => `${k}=${v}`).join("、")}；問答政策 {config.qa_policy_version}。</p>
      </div>
    </div>
  );
}
