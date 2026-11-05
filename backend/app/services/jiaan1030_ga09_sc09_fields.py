"""GA09／SC09 共用表單欄位規格（v2，依紙本原件修復）。

來源：`docs/jiaan1030_forms/678412_0.jpg`、`678413_0.jpg`（嘉安健康事業有限公司附設嘉義市
私立嘉安居家長照機構「喘息/短照服務紀錄表」實際填寫照片，表單編號 E001006），
並依第八次、第九次會議紀錄及 10/30 嘉安訪談內容交叉核對。

**已依紙本證據確認、可直接採用的部分**：
- 服務類型需顯示代碼＋中文全名（「GA09－居家喘息服務」／「SC09－居家短照服務」），非純代碼。
- 服務時間為「開始時間～結束時間」兩個 24 小時制時間欄位，不是自由文字。
- 服務內容是 13 項固定勾選項目＋「其他服務」補充文字欄，不是自由文字。
- 表單另有「區別」「長照等級（1～8 級）」「福利身分（一般／中低收入／低收入）」三個欄位，
  目前系統完全沒有。
- 簽章欄位紙本上實際分為三處（案主/親屬、照顧服務員、居服督導員），本系統維持既有
  `signature_placeholder` 佔位、不收集簽章資料，僅在說明文字中如實反映紙本有三方簽章、
  電子化簽署方式待嘉安確認。

**仍未確認、本模組刻意不編造的部分**（見 `UNCONFIRMED_FIELDS`）：各欄位是否必填、
「其他服務」補充文字的字數上限、簽章欄位的簽署流程與法規要求、一張表單紙本可彙總多組
（最多 4～5 組）不同日期/時段的服務紀錄、本系統目前採「一張草稿＝一次服務」是否需要
調整為對應紙本的彙總格式。本模組一律把 `required` 設為 `False`，待嘉安核對後再調整。

本模組只定義資料，不寫入任何資料庫；套用到 `jiaan1030_service_forms.fields_json` 時，
呼叫端必須自行確保：(1) 絕不覆蓋 `schema_status`/`reviewed` 已為 'approved'/TRUE 的既有內容，
(2) 新版本一律以未核准狀態（`draft_unverified`、`reviewed=FALSE`）呈現，不自動標示為已核准。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# 未確認事項清單（供人工審核用，非程式邏輯依賴）：
UNCONFIRMED_FIELDS = (
    "各欄位是否必填（required）",
    "「其他服務」補充文字欄位的字數上限",
    "簽章欄位的簽署流程、載具與法規要求（本版本僅佔位，不收集簽章資料）",
    "紙本一張表單可彙總最多 4～5 組不同日期/時段的服務紀錄，本系統目前「一張草稿＝一次服務」"
    "的設計是否需要調整為對應紙本的彙總格式",
)

# 依紙本確認的 13 項服務內容勾選項目（順序與紙本一致）。
SERVICE_CONTENT_ITEMS = (
    "協助如廁", "協助沐浴", "穿換衣服", "口腔清潔", "協助進食", "協助服藥",
    "翻身、拍背", "協助上下床", "陪同運動", "簡單被動式肢體關節活動",
    "協助使用日常生活輔助器具", "護理照護（限日照／機構）", "活動安排",
)


def ga09_sc09_v2_fields() -> dict[str, Any]:
    """回傳依紙本原件修復後的 GA09／SC09 共用 fields_json（v2）。

    回傳值是新物件（呼叫端可放心修改副本），符合既有 DynamicForm 的 schema：
    {"version": int, "sections": [{"key","label","fields":[{"key","label","type","required","options","max_length"}]}]}。
    """
    return {
        "version": 2,
        "sections": [
            {
                "key": "basic",
                "label": "基本資訊",
                "fields": [
                    {
                        "key": "district",
                        "label": "區別（里別／轄區，必填條件待確認）",
                        "type": "text",
                        "required": False,
                        "max_length": 50,
                    },
                    {
                        "key": "ltc_level",
                        "label": "長照等級（必填條件待確認）",
                        "type": "radio",
                        "required": False,
                        "options": [str(n) for n in range(1, 9)],
                    },
                    {
                        "key": "welfare_status",
                        "label": "福利身分（必填條件待確認）",
                        "type": "radio",
                        "required": False,
                        "options": ["一般", "中低收入", "低收入"],
                    },
                    {
                        "key": "service_type",
                        "label": "服務類型（必填條件待確認）",
                        "type": "select",
                        "required": False,
                        # 畫面顯示完整中文名稱（見 option_labels），但儲存值維持 GA09／SC09
                        # 代碼本身，與既有 API、報表及資料查詢使用的代碼保持一致，避免混淆。
                        "options": ["GA09", "SC09"],
                        "option_labels": ["GA09－居家喘息服務", "SC09－居家短照服務"],
                    },
                    {
                        "key": "service_date",
                        "label": "服務日期（必填條件待確認）",
                        "type": "date",
                        "required": False,
                    },
                    {
                        "key": "start_time",
                        "label": "開始時間（24小時制，必填條件待確認）",
                        "type": "time",
                        "required": False,
                    },
                    {
                        "key": "end_time",
                        "label": "結束時間（24小時制，必填條件待確認）",
                        "type": "time",
                        "required": False,
                    },
                ],
            },
            {
                "key": "service_content",
                "label": "服務內容（依紙本13項勾選，必填條件待確認）",
                "fields": [
                    {
                        "key": "service_items",
                        "label": "服務項目（可複選）",
                        "type": "checkbox_group",
                        "required": False,
                        "options": list(SERVICE_CONTENT_ITEMS),
                    },
                    {
                        "key": "other_service_note",
                        "label": "其他服務（補充文字，字數上限待確認，暫訂保守值）",
                        "type": "textarea",
                        "required": False,
                        "max_length": 500,
                    },
                ],
            },
            {
                "key": "signature",
                "label": "簽章",
                "fields": [
                    {
                        "key": "signature",
                        "label": "簽章欄位（紙本為案主/親屬、照顧服務員、居服督導員三方簽章；"
                                 "電子化簽署方式待嘉安確認，本系統暫不收集簽章資料）",
                        "type": "signature_placeholder",
                        "required": False,
                    },
                ],
            },
        ],
    }


def apply_draft_fields(db: Session, form_code: str, fields_json: dict[str, Any]) -> str:
    """安全套用草稿 fields_json：找不到表單回傳 'not_found'；若該表單 schema_status 已是
    'approved'（代表欄位內容已人工核對且可能已被引用），拒絕覆蓋並回傳 'skipped_approved'，
    不做任何寫入；否則更新 fields_json 並回傳 'applied'。

    只更新 fields_json 欄位本身，不動 reviewed/schema_status，由呼叫端自行 commit/rollback，
    因此永遠可回復（未 commit 前可直接 rollback；commit 後仍可用相同函式再套用先前版本還原）。
    """
    row = db.execute(
        text("SELECT schema_status FROM jiaan1030_service_forms WHERE code = :code"), {"code": form_code}
    ).mappings().first()
    if row is None:
        return "not_found"
    if row["schema_status"] == "approved":
        return "skipped_approved"
    db.execute(
        text("UPDATE jiaan1030_service_forms SET fields_json = :fields_json "
             "WHERE code = :code AND schema_status <> 'approved'"),
        {"fields_json": json.dumps(fields_json), "code": form_code},
    )
    return "applied"
