import { isInLineApp } from "./auth";

/** 錄音不可用時的替代入口：LINE 原生語音訊息、外部瀏覽器開啟。 */
export function FallbackEntry({ reason, compact = false }: { reason?: string; compact?: boolean }) {
  const url = window.location.href;
  if (compact) {
    return (
      <details className="small muted">
        <summary>錄不到音？替代方式</summary>
        <p>① 回到 LINE 聊天室，長按麥克風直接傳語音訊息給小照，後端會轉成文字。</p>
        {isInLineApp() && <p>② 在外部瀏覽器開啟本頁：<a href={url} target="_blank" rel="noreferrer">{url}</a></p>}
      </details>
    );
  }
  return (
    <div className="card stack">
      <div className="notice warn">此裝置無法在網頁錄音：{reason}</div>
      <p>請改用以下方式：</p>
      <p>① <strong>LINE 語音訊息</strong>：回到與小照的聊天室，長按麥克風錄音送出，系統會自動轉成文字並回覆。</p>
      {isInLineApp() ? (
        <p>② <strong>外部瀏覽器</strong>：複製此網址到 Chrome／Safari 開啟：<br /><a href={url} target="_blank" rel="noreferrer">{url}</a></p>
      ) : (
        <p>② 請確認瀏覽器已允許麥克風權限，並使用 HTTPS 網址。</p>
      )}
      <p className="small muted">iOS／Android 的 LINE 內建瀏覽器錄音支援度尚未實機驗證（見 docs/acceptance.md）。</p>
    </div>
  );
}
