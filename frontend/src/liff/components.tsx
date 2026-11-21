import { publicDisplayText } from '../publicText';
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage, isApiError, newRequestId, post, type Answer, type Citation } from "../api";
import { isInLineApp } from "./auth";
import { FeedbackCollector } from "../quality/FeedbackCollector";

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="notice danger">{errorMessage(error)}</div>;
}

export function CitationCard({ c, index }: { c: Citation; index: number }) {
  const sourceTypes: Record<string, string> = { regulation: '政府法規', internal_rule: '機構內規', sop: '作業程序', other: '其他文件' };
  const [open, setOpen] = useState(false);
  const [full, setFull] = useState<{
    chunk: { text: string };
    context: { locator: string; text: string; is_target: boolean }[];
    document: { title: string; doc_type: string };
    version: { file_url: string; source_url: string | null; version_label: string; status: string; effective_from: string | null; effective_to: string | null; source: string | null };
    official_source?: { title: string; official_url: string; verified: boolean } | null;
  } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const publicTitle = /^STUST[_-]/i.test(c.document_title) ? "系統保存文件" : c.document_title;
  const publicLocator = /(?:chunk|segment|uuid|[0-9a-f]{8}-[0-9a-f-]{27,})/i.test(c.locator) ? "" : c.locator;
  const publicExcerpt = c.excerpt.replace(/\s+/g, " ").trim();
  const load = () => {
    setOpen(true);
    if (!full) api<typeof full>(c.source_url).then(setFull).catch(setError);
  };
  return (
    <div className="cite">
      <div className="title">出處 {index}：{publicTitle}</div>
      <span className="tag">{sourceTypes[c.doc_type] ?? '來源類型待確認'}</span>
      <div className="small">
        {publicLocator ? `${publicLocator}｜` : ""}版本 {c.version_label}｜生效日 {c.effective_from ?? "未填"}
        {c.effective_to ? `～${c.effective_to}` : ""}
        {c.version_status !== "published" ? <span className="tag warn">此版本已{c.version_status === "deactivated" ? "停用" : "變更"}（歷史引用）</span> : null}
      </div>
      <p className="small muted">{publicExcerpt}</p>
      {!open ? (
        <button className="btn" onClick={load}>查看引用與文件來源</button>
      ) : (
        <div className="stack">
          <ErrorBox error={error} />
          {full?.context.map((seg) => (
            <p key={seg.locator} className={seg.is_target ? "" : "muted small"} style={{ whiteSpace: "pre-wrap" }}>
              <strong>{seg.locator}</strong>
              <br />
              {seg.text}
            </p>
          ))}
          {full && (
            <div className="stack">
              <div className="row">
                {full.official_source?.verified === true && full.official_source.official_url ? (
                  <a className="btn primary" href={full.official_source.official_url} target="_blank" rel="noopener noreferrer">查看官方原文</a>
                ) : (
                  full.version.source_url && /^https:\/\/(?:law\.moj\.gov\.tw|(?:www\.)?mohw\.gov\.tw|dep\.mohw\.gov\.tw|1966\.gov\.tw|www\.klchb\.klcg\.gov\.tw|www\.klcg\.gov\.tw|ws\.tycg\.gov\.tw|www\.ntshb\.gov\.tw)\//i.test(full.version.source_url) ? (
                    <a className="btn"
     href={xzFindOfficialCitationLink(c, full) || full.version.source_url}
     target="_blank" rel="noopener noreferrer">
  {xzFindOfficialCitationLink(c, full) ? "查看官方來源頁面（核對表）" : "查看官方來源頁面（待核對）"}
</a>
                  ) : (
                    <span className="notice warn small">{(() => {
    const reviewedSource = xzFindOfficialCitationLink(c as unknown, full as unknown);
    // Source page matches the reviewed Excel row; no separate PDF button here.
    return reviewedSource ? (
      <a href={reviewedSource} target="_blank" rel="noopener noreferrer"
         style={{color: "#9a3412", textDecoration: "underline", fontWeight: 700}}>
        查看官方來源頁面（核對表）
      </a>
    ) : (
      "官方來源尚待確認，目前可查看系統保存的文件。"
    );
  })()}</span>
                  )
                )}
                {full.version.file_url ? (
                <button
                  className="btn"
                  onClick={async () => {
                    // Reserve a window while the click still has browser user activation.
                    const inLineApp = isInLineApp();
                    const reserved = inLineApp ? null : window.open("about:blank", "_blank");
                    if (reserved) reserved.opener = null;
                    try {
                      setError(null);
                      // liff.isInClient() requires liff.init() to have run first, which
                      // never happens for a password-logged-in supervisor/director/admin
                      // session (they never go through loginWithLiff()). Calling it then
                      // throws, which used to land in the catch below -- after the
                      // download-url call below had already succeeded -- and show "無法
                      // 開啟原文連結" even though the real backend chain was fine.
                      // isInLineApp() (a plain user-agent check) decides this instead; the
                      // SDK is only imported/used when actually inside the LINE app.
                      const result = await post<{ url: string }>(
                        full.version.file_url.replace(/\/file$/, "/download-url"), {},
                      );
                      if (inLineApp) {
                        const liff = (await import("@line/liff")).default;
                        reserved?.close();
                        liff.openWindow({ url: result.url, external: true });
                      } else {
                        const opened = reserved ?? window.open(result.url, "_blank");
                        if (!opened) throw new Error("blocked");
                        opened.opener = null;
                        if (reserved) reserved.location.href = result.url;
                      }
                    } catch (e) {
                      reserved?.close();
                      if (isApiError(e) && e.status === 404) {
                        setError(new Error("目前未提供原文連結"));
                      } else {
                        setError(new Error("無法開啟原文連結，請稍後再試。"));
                      }
                    }
                  }}
                >
                  查看系統保存版本
                </button>
              ) : (
                <span className="tag warn">系統保存版本目前無法開啟</span>
              )}
              </div>
              <details>
                <summary>查看文件資訊</summary>
                <dl className="small" style={{ margin: "8px 0 0" }}>
                  <dt><strong>文件正式名稱</strong></dt><dd>{full.document.title}</dd>
                  <dt><strong>來源機關</strong></dt><dd>{full.version.source ?? "尚未填寫"}</dd>
                  <dt><strong>文件類型</strong></dt><dd>{sourceTypes[full.document.doc_type] ?? "其他文件"}</dd>
                  <dt><strong>版本／生效日期</strong></dt><dd>{full.version.version_label}／{full.version.effective_from ?? "尚未填寫"}</dd>
                  <dt><strong>官方來源審核狀態</strong></dt><dd>{full.official_source?.verified === true ? "已核准" : "待確認"}</dd>
                  <dt><strong>差異提醒</strong></dt><dd>{full.official_source?.verified === true
                    ? "官方網站可能持續更新；系統保存版本是本次回答實際引用的固定版本。"
                    : "尚未完成官方來源核對；系統保存版本是本次回答實際引用的文件，不代表已核准的官方原文。"}</dd>
                </dl>
              </details>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** 語音播放：使用者點選才產生與播放；失敗時不影響文字。 */
export function TtsButton({ answer, autoPlay = false }: { answer: Answer; autoPlay?: boolean }) {
  const [state, setState] = useState<{ status: string; audio_url: string | null; error: string | null }>(
    answer.tts ?? { status: "none", audio_url: null, error: null },
  );
  const [busy, setBusy] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const poll = useRef<number | null>(null);

  // 父層重新取得回答（例如頁面重載後）時，同步語音狀態
  useEffect(() => {
    if (answer.tts) setState(answer.tts);
  }, [answer.tts]);

  const request = async () => {
    setBusy(true);
    try {
      const result = await post<typeof state>(`/api/qa/${answer.id}/tts`, {});
      setState(result);
    } catch (e) {
      setState({ status: "failed", audio_url: null, error: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (state.status === "queued" || state.status === "running") {
      poll.current = window.setTimeout(async () => {
        try {
          setState(await api<typeof state>(`/api/qa/${answer.id}/tts`));
        } catch {
          /* 下一輪再試 */
        }
      }, 1500);
    }
    return () => {
      if (poll.current) window.clearTimeout(poll.current);
    };
  }, [state, answer.id]);

  useEffect(() => {
    if (autoPlay && state.status === "none" && !busy) void request();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPlay]);

  useEffect(() => {
    if (autoPlay && state.status === "ready" && audioRef.current) {
      audioRef.current.play().catch(() => undefined); // 自動播放被擋時，使用者仍可手動按播放
    }
  }, [autoPlay, state.status]);

  if (!answer.answer_text) return null;
  if (state.status === "ready" && state.audio_url) {
    return <audio ref={audioRef} controls preload="none" src={state.audio_url} style={{ width: "100%" }} />;
  }
  return (
    <div className="stack">
      <button className="btn" onClick={request} disabled={busy || state.status === "queued" || state.status === "running"}>
        🔊 {state.status === "queued" || state.status === "running" ? "語音產生中…" : state.status === "failed" ? "語音失敗，再試一次" : "播放語音"}
      </button>
      {state.status === "failed" && <div className="notice warn">語音產生失敗（{state.error ?? "未知原因"}），請直接閱讀文字。</div>}
    </div>
  );
}

/** 「送交督導確認」：建案成功才顯示已送交；失敗顯示真實狀態與重試。 */
export function EscalateButton({ answer, onChange }: { answer: Answer; onChange: (a: Answer) => void }) {
  const [note, setNote] = useState("");
  if (answer.outcome === "clarify") return null;
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const requestId = useRef(newRequestId());
  const existing = answer.manual_case ?? (answer.outcome === "escalated" ? answer.case : null);
  if (existing) {
    return (
      <div className="notice ok">
        已送交督導確認（案件 {existing.number}，{existing.status_label}）。<Link to={`/liff/cases/${existing.id}`}>查看案件</Link>
      </div>
    );
  }
  if (answer.outcome === "escalation_failed") {
    return (
      <div className="stack">
        <div className="notice danger">⚠ 尚未送交督導：{answer.case_error}</div>
        <ErrorBox error={error} />
        <button
          className="btn primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              onChange(await post<Answer>(`/api/qa/${answer.id}/retry-escalation`, {}));
            } catch (e) {
              setError(e);
            } finally {
              setBusy(false);
            }
          }}
        >
          重試送交
        </button>
      </div>
    );
  }
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await post(`/api/qa/${answer.id}/escalate`, { note, client_request_id: requestId.current });
      onChange(await api<Answer>(`/api/qa/${answer.id}`));
    } catch (e) {
      setError(e); // 建案失敗：顯示真實狀態，可用同一 request id 重試
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="stack">
      {!open ? (
        <button className="btn" onClick={() => setOpen(true)}>📨 送交督導確認</button>
      ) : (
        <>
          <textarea placeholder="補充說明（選填；請用「住民」「家屬」代稱，不要寫姓名或房號）" value={note} onChange={(e) => setNote(e.target.value)} />
          <ErrorBox error={error} />
          <div className="row">
            <button className="btn primary" onClick={submit} disabled={busy}>{busy ? "送交中…" : error ? "再試一次" : "確認送交"}</button>
            <button className="btn" onClick={() => setOpen(false)} disabled={busy}>取消</button>
          </div>
        </>
      )}
    </div>
  );
}

export function WrongButton({ answer, onChange }: { answer: Answer; onChange: (a: Answer) => void }) {
  return <FeedbackCollector key={answer.id} answer={answer} onChange={onChange} />;
}

export function AnswerCard({ answer, onChange, autoPlay = false }: { answer: Answer; onChange: (a: Answer) => void; autoPlay?: boolean }) {
  const escalated = answer.outcome === "escalated" || answer.outcome === "escalation_failed";
  const clarify = answer.outcome === "clarify";
  return (
    <div className="card stack">
      <div className="row">
        <span className="tag ai">{answer.label}</span>
        {answer.modes.llm !== "ollama" && <span className="tag mock">LLM={answer.modes.llm}</span>}
        {answer.wake_word && <span className="tag">已辨識喚醒詞</span>}
      </div>
      <p className="muted small">問：{answer.question_masked}</p>
      {clarify ? (
        <div className="notice">{publicDisplayText(answer.answer_text)}</div>
      ) : escalated ? (
        <div className={`notice ${answer.outcome === "escalation_failed" ? "danger" : "warn"}`}>{publicDisplayText(answer.answer_text)}</div>
      ) : (
        <div className="stack">
          {answer.claims.map((c, i) => (
            <div key={i} className="claim">
              {c.text}
              <span className="muted small">（出處 {c.citations.map((x) => x.replace("c", "")).join("、")}）</span>
            </div>
          ))}
          {answer.safety_notice && <div className="notice">{answer.safety_notice}</div>}
          {answer.citations.map((c, i) => (
            <CitationCard key={c.id} c={c} index={i + 1} />
          ))}
        </div>
      )}
      <TtsButton answer={answer} autoPlay={autoPlay} />
      <EscalateButton answer={answer} onChange={onChange} />
      <div className="row">
        <WrongButton answer={answer} onChange={onChange} />
        <Link className="btn" to="/liff/ask">💬 繼續提問</Link>
      </div>
      <p className="small muted">AI 初步參考不是最終決定；實際做法請依督導確認與機構規定。</p>
    </div>
  );
}


// XZ_OFFICIAL_LINKS_20261115_START
// Links come from the user's reviewed worksheet. A link is not a system approval.
const xzOfficialLinks: Array<{title: string; url: string; aliases: string[]}> = [
  {
    "title": "長照專業服務操作指引－觀念篇",
    "url": "https://1966.gov.tw/LTC/cp-6451-70123-207.html",
    "aliases": [
      "長照專業服務操作指引－觀念篇",
      "1.長照專業服務操作指引-觀念篇_公告"
    ]
  },
  {
    "title": "長照專業服務操作指引－居家護理指導與諮詢",
    "url": "https://1966.gov.tw/LTC/cp-6451-70123-207.html",
    "aliases": [
      "長照專業服務操作指引－居家護理指導與諮詢",
      "3.長照專業服務操作指引-操作篇-居家護理指導與諮詢操作指引_公告"
    ]
  },
  {
    "title": "BA08足部照護及BA17協助執行輔助性醫療資格疑義",
    "url": "https://mohwlaw.mohw.gov.tw/FINT/FINTQRY04.aspx?starDate=00000000&endDate=99991231&no=&n1=&n2=1081960980&kt=&kw=&kw2=&kw3=&kw4=&valid=3&type=etype_&RowNo=1",
    "aliases": [
      "BA08足部照護及BA17協助執行輔助性醫療資格疑義",
      "BA08足部照護及BA17協助執行輔助性醫療資格疑義-衛部顧字第1081960980號"
    ]
  },
  {
    "title": "執行陪同外出BA13之定期式復健疑義",
    "url": "https://mohwlaw.mohw.gov.tw/FINT/FINTQRY04.aspx?starDate=00000000&endDate=99991231&no=&n1=&n2=1131963191&kt=&kw=&kw2=&kw3=&kw4=&valid=3&type=etype_&RowNo=1",
    "aliases": [
      "執行陪同外出BA13之定期式復健疑義",
      "執行陪同外出BA13之定期式復健疑義-衛部顧字第1131963191號"
    ]
  },
  {
    "title": "居家喘息服務實務使用疑義－口腔抽吸",
    "url": "https://mohwlaw.mohw.gov.tw/FINT/FINTQRY04.aspx?starDate=00000000&endDate=99991231&no=&n1=&n2=1091961599&kt=&kw=&kw2=&kw3=&kw4=&valid=3&type=etype_&RowNo=1",
    "aliases": [
      "居家喘息服務實務使用疑義－口腔抽吸",
      "居家喘息服務實務使用疑義-口腔抽吸-衛部顧字第1091961599號"
    ]
  },
  {
    "title": "居家式喘息服務進食服務疑義",
    "url": "https://mohwlaw.mohw.gov.tw/FINT/FINTQRY04.aspx?starDate=00000000&endDate=99991231&no=&n1=&n2=1091962544&kt=&kw=&kw2=&kw3=&kw4=&valid=3&type=etype_&RowNo=1",
    "aliases": [
      "居家式喘息服務進食服務疑義",
      "居家式喘息服務進食服務疑義-衛部顧字第1091962544號"
    ]
  },
  {
    "title": "居家服務督導員工作手冊",
    "url": "https://1966.gov.tw/LTC/cp-7565-86698-207.html",
    "aliases": [
      "居家服務督導員工作手冊"
    ]
  },
  {
    "title": "照顧服務員伸入肛門清除糞便行為疑義",
    "url": "https://mohwlaw.mohw.gov.tw/FINT/FINTQRY04.aspx?starDate=00000000&endDate=99991231&no=&n1=&n2=1131962666&kt=&kw=&kw2=&kw3=&kw4=&valid=3&type=etype_&RowNo=1",
    "aliases": [
      "照顧服務員伸入肛門清除糞便行為疑義",
      "照顧服務員伸入肛門清除糞便行為疑義-衛部顧字第1131962666號"
    ]
  },
  {
    "title": "照顧服務員執行傷口換藥疑義",
    "url": "https://1966.gov.tw/ltc/cp-7615-87882-207.html",
    "aliases": [
      "照顧服務員執行傷口換藥疑義",
      "照顧服務員執行傷口換藥疑義-_1090119919_"
    ]
  },
  {
    "title": "長照專業服務手冊",
    "url": "https://1966.gov.tw/LTC/cp-6451-70123-207.html",
    "aliases": [
      "長照專業服務手冊"
    ]
  },
  {
    "title": "長照專業服務操作指引－共通操作指引",
    "url": "https://1966.gov.tw/LTC/cp-6451-70123-207.html",
    "aliases": [
      "長照專業服務操作指引－共通操作指引",
      "長照專業服務操作指引-操作篇-共通操作指引_公告"
    ]
  },
  {
    "title": "長照專業服務操作指引－附錄一服務紀錄參考格式",
    "url": "https://1966.gov.tw/LTC/cp-6451-70123-207.html",
    "aliases": [
      "長照專業服務操作指引－附錄一服務紀錄參考格式",
      "長照專業服務操作指引-附錄一服務紀錄參考格式_公告",
      "附錄一服務紀錄參考格式 長照專業服務操作指引"
    ]
  },
  {
    "title": "長照專業服務操作指引－附錄三案例說明",
    "url": "https://1966.gov.tw/LTC/cp-6451-70123-207.html",
    "aliases": [
      "長照專業服務操作指引－附錄三案例說明",
      "長照專業服務操作指引-附錄三-案例說明_公告",
      "附錄三案例說明 長照專業服務操作指引"
    ]
  },
  {
    "title": "長照專業服務操作指引－附錄二居家護理指導與諮詢服務的處置指引",
    "url": "https://1966.gov.tw/LTC/cp-6451-70123-207.html",
    "aliases": [
      "長照專業服務操作指引－附錄二居家護理指導與諮詢服務的處置指引",
      "長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告",
      "附錄二居家護理指導與諮詢服務的處置指引 長照專業服務操作指引"
    ]
  },
  {
    "title": "115年度居家式長期照顧服務機構評鑑基準－附件一",
    "url": "https://1966.gov.tw/LTC/cp-6457-69929-207.html",
    "aliases": [
      "115年度居家式長期照顧服務機構評鑑基準－附件一",
      "附件一-115年度居家式長期照顧服務機構評鑑基準",
      "附件一 115年度居家式長期照顧服務機構評鑑基準"
    ]
  },
  {
    "title": "陪同外出BA13及陪同就醫BA14相關疑義",
    "url": "https://mohwlaw.mohw.gov.tw/FINT/FINTQRY04.aspx?starDate=00000000&endDate=99991231&no=&n1=&n2=1131961919&kt=&kw=&kw2=&kw3=&kw4=&valid=3&type=etype_&RowNo=1",
    "aliases": [
      "陪同外出BA13及陪同就醫BA14相關疑義",
      "陪同外出BA13及陪同就醫BA14相關疑義-衛部顧字第1131961919號"
    ]
  },
  {
    "title": "長期照顧服務人員訓練認證繼續教育及登錄辦法",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070045",
    "aliases": [
      "長期照顧服務人員訓練認證繼續教育及登錄辦法"
    ]
  },
  {
    "title": "長期照顧服務機構設立標準",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070048",
    "aliases": [
      "長期照顧服務機構設立標準"
    ]
  },
  {
    "title": "長期照顧服務機構設立許可及管理辦法",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070044",
    "aliases": [
      "長期照顧服務機構設立許可及管理辦法"
    ]
  },
  {
    "title": "長期照顧服務法",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070040",
    "aliases": [
      "長期照顧服務法"
    ]
  },
  {
    "title": "長期照顧服務法施行細則",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070043",
    "aliases": [
      "長期照顧服務法施行細則"
    ]
  },
  {
    "title": "長期照顧服務申請及給付辦法",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070059",
    "aliases": [
      "長期照顧服務申請及給付辦法"
    ]
  },
  {
    "title": "居家式長照機構設立標準表－附件一",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070048",
    "aliases": [
      "居家式長照機構設立標準表－附件一",
      "附件一_居家式長照機構設立標準表",
      "附件一 居家式長照機構設立標準表"
    ]
  },
  {
    "title": "長照人員資格－附件一",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070045",
    "aliases": [
      "長照人員資格－附件一",
      "附件一_長照人員資格",
      "附件一 長照人員資格"
    ]
  },
  {
    "title": "長照人員繼續教育辦理機構、實施方式及積分採認與抵免表－附件二",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070045",
    "aliases": [
      "長照人員繼續教育辦理機構、實施方式及積分採認與抵免表－附件二",
      "附件二__長照人員繼續教育之辦理機構與實施方式及積分採認與抵免表",
      "附件二 長照人員繼續教育辦理機構、實施方式及積分採認與抵免表"
    ]
  },
  {
    "title": "照顧問題清單－附表一",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070059",
    "aliases": [
      "照顧問題清單－附表一",
      "附表一_照顧問題清單",
      "附表一 照顧問題清單"
    ]
  },
  {
    "title": "交通接送服務給付分區表－附表三",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070059",
    "aliases": [
      "交通接送服務給付分區表－附表三",
      "附表三_交通接送服務給付分區表",
      "附表三 交通接送服務給付分區表"
    ]
  },
  {
    "title": "長照需要等級及長照服務給付項目之額度－附表二",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070059",
    "aliases": [
      "長照需要等級及長照服務給付項目之額度－附表二",
      "附表二_長照需要等級及長照服務給付項目之額度",
      "附表二 長照需要等級及長照服務給付項目之額度"
    ]
  },
  {
    "title": "部分負擔比率－附表五",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070059",
    "aliases": [
      "部分負擔比率－附表五",
      "附表五_部分負擔比率",
      "附表五 部分負擔比率"
    ]
  },
  {
    "title": "原民區或離島範圍－附表六",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070059",
    "aliases": [
      "原民區或離島範圍－附表六",
      "附表六_原民區或離島範圍",
      "附表六 原民區或離島範圍"
    ]
  },
  {
    "title": "照顧組合表－智慧科技輔具－附表四之一",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070059",
    "aliases": [
      "照顧組合表－智慧科技輔具－附表四之一",
      "附表四之一_照顧組合表-智慧科技輔具",
      "附表四之一 照顧組合表 智慧科技輔具"
    ]
  },
  {
    "title": "照顧組合表－附表四",
    "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070059",
    "aliases": [
      "照顧組合表－附表四",
      "附表四_照顧組合表",
      "附表四 照顧組合表"
    ]
  }
];

function xzNormalizeSourceName(value: unknown): string {
  return String(value ?? "")
    .normalize("NFKC")
    .replace(/\.(pdf|txt|docx?)$/i, "")
    .replace(/[\s\u3000_\-－–—:：()（）\[\]【】.．、，,]/g, "")
    .toLowerCase();
}

function xzFindOfficialCitationLink(citation: unknown, details: unknown): string | null {
  const values: string[] = [];
  for (const obj of [citation, details]) {
    if (!obj || typeof obj !== "object") continue;
    const x = obj as Record<string, unknown>;
    for (const key of ["title", "document_title", "source_title", "file_name", "filename", "source_name", "document_name", "name"]) {
      if (typeof x[key] === "string") values.push(x[key] as string);
    }
    if (x.document && typeof x.document === "object") {
      const d = x.document as Record<string, unknown>;
      if (typeof d.title === "string") values.push(d.title);
    }
  }
  const targets = values.map(xzNormalizeSourceName).filter(Boolean);
  let hit: {url: string; strength: number} | null = null;
  for (const row of xzOfficialLinks) {
    for (const alias of row.aliases) {
      const key = xzNormalizeSourceName(alias);
      if (key.length < 5) continue;
      for (const name of targets) {
        // Prefer exact match; conservative partial match for titled citations.
        const strength = name === key ? 10000 + key.length : (name.includes(key) && key.length >= 8 ? key.length : 0);
        if (strength > (hit?.strength ?? 0)) hit = {url: row.url, strength};
      }
    }
  }
  return hit?.url ?? null;
}
// XZ_OFFICIAL_LINKS_20261115_END

