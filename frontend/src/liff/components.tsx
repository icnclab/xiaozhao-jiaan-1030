import { publicDisplayText } from '../publicText';
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage, newRequestId, post, type Answer, type Citation } from "../api";
import { isInLineApp } from "./auth";
import { FeedbackCollector } from "../quality/FeedbackCollector";

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="notice danger">{errorMessage(error)}</div>;
}

export function CitationCard({ c, index }: { c: Citation; index: number }) {
  const sourceTypes: Record<string, string> = { regulation: '政府法規', internal_rule: '機構內規', sop: '作業程序', other: '其他文件' };
  const [open, setOpen] = useState(false);
  const [full, setFull] = useState<{ chunk: { text: string }; context: { locator: string; text: string; is_target: boolean }[]; version: { file_url: string; source_url: string | null }; official_source?: { title: string; official_url: string; verified: boolean } | null } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = () => {
    setOpen(true);
    if (!full) api<typeof full>(c.source_url).then(setFull).catch(setError);
  };
  return (
    <div className="cite">
      <div className="title">出處 {index}：{c.document_title}</div>
      <span className="tag">{sourceTypes[c.doc_type] ?? '來源類型待確認'}</span>
      <div className="small">
        {c.locator}｜版本 {c.version_label}｜生效日 {c.effective_from ?? "未填"}
        {c.effective_to ? `～${c.effective_to}` : ""}
        {c.version_status !== "published" ? <span className="tag warn">此版本已{c.version_status === "deactivated" ? "停用" : "變更"}（歷史引用）</span> : null}
      </div>
      <p className="small muted">{c.excerpt}</p>
      {!open ? (
        <button className="btn" onClick={load}>查看原文</button>
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
            <div className="row">
              <button
                className="btn"
                onClick={async () => {
                  // Reserve a window while the click still has browser user activation.
                  const reserved = isInLineApp() ? null : window.open("about:blank", "_blank");
                  if (reserved) reserved.opener = null;
                  try {
                    setError(null);
                    const liff = (await import("@line/liff")).default;
                    const result = await post<{ url: string }>(
                      full.version.file_url.replace(/\/file$/, "/download-url"), {},
                    );
                    if (liff.isInClient()) {
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
                    setError(new Error("無法開啟下載，請稍後再試。"));
                  }
                }}
              >
                下載原始檔
              </button>
              {full.official_source?.verified === true && full.official_source.official_url ? (
                <a className="btn" href={full.official_source.official_url} target="_blank" rel="noopener noreferrer">開啟已審核官方原文</a>
              ) : (
                <span className="tag warn">尚無已審核官方原文連結，請以上方原文或「下載原始檔」為準</span>
              )}
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
