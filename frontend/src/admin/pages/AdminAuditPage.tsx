import { useEffect, useState } from "react";
import { api } from "../../api";
import { ErrorBox } from "../../liff/components";
import { useAdmin } from "../AdminApp";

interface AuditRow {
  id: number;
  created_at: string;
  action: string;
  outcome: string | null;
  actor_role: string | null;
  actor: string | null;
  target_type: string | null;
  target_id: string | null;
  meta: Record<string, unknown>;
}

/** 對照表窮舉自後端 audit.record() 實際使用的action字串（見 app/services/*.py、app/api/*.py）；
 * 沒有對照到的action保留原字串顯示，不隱藏、不假裝有翻譯。 */
const ACTION_LABELS: Record<string, string> = {
  "auth.login": "管理員登入", "auth.liff_login": "LINE登入", "auth.sos_login": "SOS登入",
  "auth.bind": "LINE帳號綁定", "auth.binding_code": "產生綁定碼", "auth.admin_revoke_sessions": "強制登出帳號",
  "case.create": "建立案件", "case.assign": "指派案件", "case.take": "接手案件",
  "case.reply": "回覆案件", "case.close": "結案", "case.caregiver_message": "照服員補充留言",
  "category.create": "新增問題分類", "category.update": "更新問題分類",
  "doc.create": "建立知識庫文件", "doc.upload": "上傳文件版本", "doc.publish": "發布文件版本",
  "doc.deactivate": "停用文件版本", "doc.update_meta": "更新文件資訊",
  "feedback.review": "審核AI回答回饋",
  "qa.ask": "AI問答", "qa.feedback": "AI回答回饋",
  "source.view": "查看引用來源", "source.download": "下載引用文件",
  "transcript.confirm": "確認錄音逐字稿", "transcript.cancel": "取消錄音逐字稿",
  "audio.upload": "上傳語音錄音", "audio.retry": "重試語音轉文字", "tts.request": "語音播放請求",
  "user.create": "建立使用者帳號", "user.delete": "刪除使用者帳號", "user.active": "啟用／停用帳號",
  "user.line_unbind": "解除LINE綁定", "user.sos_password_set": "設定SOS登入密碼",
  "line.webhook": "LINE訊息進站", "line.unfollow": "使用者封鎖LINE官方帳號",
  "notification.retry": "重送通知", "deid.term_add": "新增去識別化詞彙", "access_denied": "拒絕未授權存取",
  "quality.feedback.submit": "送出AI回答品質回饋", "quality.feedback.review": "審核AI回答品質回饋",
  "quality.dataset.export": "匯出品質資料", "quality.dataset.gold_export": "匯出核准品質資料",
  "jiaan1030_ba_service.approve": "核准BA服務項目",
  "jiaan1030_client.create": "建立服務個案", "jiaan1030_client.grant": "授予個案存取權",
  "jiaan1030_client.revoke": "撤銷個案存取權", "jiaan1030_draft.create": "建立服務紀錄草稿",
  "jiaan1030_draft.update": "更新服務紀錄草稿", "jiaan1030_draft.submit": "送出服務紀錄",
  "jiaan1030_draft.forbidden": "拒絕未授權服務紀錄操作", "jiaan1030_form.approve": "核准服務表單",
  "interaction.start": "開始跨居督存取", "interaction.end": "結束跨居督存取",
  "interaction.access_request": "申請跨居督存取", "interaction.access_approve": "核准跨居督存取",
  "interaction.access_revoke": "撤銷跨居督存取", "interaction.read": "讀取跨居督資料",
  "interaction.list": "列出跨居督資料", "interaction.technical": "跨居督技術操作",
  "interaction.legacy": "跨居督舊版操作",
};

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}
const OUTCOME_LABELS: Record<string, string> = { ok: "成功", failed: "失敗", denied: "已拒絕" };
const ROLE_LABELS: Record<string, string> = { admin: "管理員", director: "主任", supervisor: "督導", caregiver: "照服員" };

export function AdminAuditPage() {
  const { user } = useAdmin();
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [action, setAction] = useState("");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (user.role !== "admin") return;
    const qs = action ? `?action=${encodeURIComponent(action)}` : "";
    api<AuditRow[]>(`/api/admin/audit${qs}`).then(setRows).catch(setError);
  }, [action, user.role]);

  if (user.role !== "admin") {
    return (
      <div className="stack">
        <h1>操作紀錄</h1>
        <div className="notice warn">
          操作紀錄目前僅限系統管理員查看（技術設定／帳號維運範疇，與主任的機構業務管理權限分開設計）。
          若業務稽核也需要主任查看，請先與嘉安確認權限範圍，再調整後端角色設定，不由前端自行放寬。
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <h1>操作紀錄</h1>
      <p className="small muted">顯示本機構最近 200 筆操作。完整安全稽核資料仍由系統保留，這裡只呈現日常查核需要的資訊。</p>
      <div className="row">
        <select aria-label="操作類別" value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">全部操作</option>
          {Object.entries(ACTION_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>
      <ErrorBox error={error} />
      {!rows ? <p className="muted">載入中…</p> : rows.length === 0 ? (
        <p className="muted">查無符合條件的紀錄。</p>
      ) : (
        <table>
          <thead>
            <tr><th>時間</th><th>操作內容</th><th>操作人員</th><th>身分</th><th>結果</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{new Date(r.created_at).toLocaleString("zh-TW")}</td>
                <td>{actionLabel(r.action)}</td>
                <td>{r.actor ?? "—"}</td>
                <td>{r.actor_role ? ROLE_LABELS[r.actor_role] ?? r.actor_role : "—"}</td>
                <td>{r.outcome ? OUTCOME_LABELS[r.outcome] ?? r.outcome : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
