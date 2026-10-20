"""LINE webhook 事件：快速落地（API 端）與背景處理（worker 端）。

API 端只做三件事：驗簽（在路由層）、以 webhookEventId 去重寫入事件、排入工作，然後立即回 200。
長工作（STT、RAG）在 worker 執行；reply token 只在事件後短時間內使用，逾時改用 push。
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit
import ipaddress

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.line.client import ContentUnavailable, get_line_client
from app.models import (
    Case,
    Chunk,
    Citation,
    Document,
    DocumentVersion,
    Feedback,
    LineAccount,
    LineEvent,
    NotificationJob,
    QaItem,
    Transcript,
    User,
)
from app.security import decrypt_json, encrypt_json
from app.services import audit, jobs, qa_service, transcripts, tts_service
from app.services.cases import CaseError
from app.services.notifications import liff_url
from app.services.wake import greeting_reply, strip_wake_word

REPLY_TOKEN_SAFE_SEC = 50
PRIVACY_HINT = "提醒：在 LINE 聊天室傳的文字與語音會經 LINE 平臺傳遞，請用「住民」「家屬」代稱，不要說姓名或房號。"
MENU_KEYWORDS = {
    "問 AI": ("ask", "開啟提問頁"),
    "問AI": ("ask", "開啟提問頁"),
    "錄音": ("record", "開啟錄音／談話紀錄頁"),
    "談話紀錄": ("record", "開啟錄音／談話紀錄頁"),
    "問題分類": ("report", "開啟問題分類回報頁"),
    "我的案件": ("cases", "開啟我的案件"),
    "使用說明": ("help", "開啟使用說明與知識庫涵蓋範圍"),
}


def store_events(session: Session, payload: dict[str, Any]) -> tuple[int, int]:
    """把 webhook 事件寫入事件表並排工作（以 webhookEventId 去重）。

    Args:
        session: ORM session（本函式會 commit）。
        payload: 已驗簽的 webhook JSON。

    Returns:
        (新事件數, 重送／重複事件數)。
    """
    new_count, duplicate_count = 0, 0
    for event in payload.get("events", []):
        event_id = event.get("webhookEventId")
        if not event_id:
            continue
        message = event.get("message") or {}
        content = None
        if message.get("type") == "text":
            content = {"text": message.get("text", "")[:2000]}
        elif event.get("type") == "postback":
            content = {"data": (event.get("postback") or {}).get("data", "")[:300]}
        timestamp = event.get("timestamp")
        statement = (
            insert(LineEvent)
            .values(
                id=uuid.uuid4(),
                webhook_event_id=event_id,
                event_type=event.get("type", "unknown")[:30],
                message_type=message.get("type"),
                message_id=message.get("id"),
                line_user_id=(event.get("source") or {}).get("userId"),
                reply_token=event.get("replyToken"),
                is_redelivery=bool((event.get("deliveryContext") or {}).get("isRedelivery")),
                content_provider=(message.get("contentProvider") or {}).get("type"),
                payload_encrypted=encrypt_json(content) if content else None,
                status="received",
                event_timestamp=datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc) if timestamp else None,
            )
            .on_conflict_do_update(
                index_elements=["webhook_event_id"],
                set_={"redelivery_count": LineEvent.redelivery_count + 1},
            )
            .returning(LineEvent.id, LineEvent.redelivery_count)
        )
        row = session.execute(statement).first()
        if row.redelivery_count == 0:
            new_count += 1
            jobs.enqueue(session, "line_event", {"line_event_id": str(row.id)}, f"line_event:{event_id}")
        else:
            duplicate_count += 1
    audit.record(session, "line.webhook", outcome="ok", meta={"new": new_count, "duplicate": duplicate_count})
    session.commit()
    return new_count, duplicate_count


def _user_for(session: Session, line_user_id: str | None) -> User | None:
    if not line_user_id:
        return None
    account = session.scalar(select(LineAccount).where(LineAccount.line_user_id == line_user_id))
    if account is None:
        return None
    user = session.get(User, account.user_id)
    return user if user and user.is_active else None


def _respond(session: Session, event: LineEvent, user: User | None, messages: list[dict[str, Any]],
             source_type: str, source_id: uuid.UUID) -> str:
    """reply token 仍新鮮就 reply，否則走通知工作 push。回傳實際路徑。"""
    fresh = event.event_timestamp and (time.time() - event.event_timestamp.timestamp()) < REPLY_TOKEN_SAFE_SEC
    if event.reply_token and fresh:
        result = get_line_client(session).reply(event.reply_token, messages)
        event.reply_token = None
        if result.accepted:
            return "reply"
    if user is None:
        return "dropped_no_user"
    notification = NotificationJob(
        org_id=user.org_id, recipient_id=user.id, source_type=source_type, source_id=source_id, channel="line",
        status="queued", payload={"kind": "answer", "messages": messages},
    )
    session.add(notification)
    session.flush()
    jobs.enqueue(session, "notify", {"notification_id": str(notification.id)}, f"notify:{notification.id}")
    return "push_queued"


def _text(message: str, quick: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"type": "text", "text": message[:4900]}
    if quick:
        body["quickReply"] = {"items": [{"type": "action", "action": a} for a in quick[:13]]}
    return body


def answer_messages(session: Session, item: QaItem, case: Case | None) -> list[dict[str, Any]]:
    """把問答結果組成 LINE 訊息（附出處摘要與 LIFF 原文入口）。"""
    qa = str(item.id)
    if item.outcome == "answered":
        rows = session.execute(
            select(Citation.label, Document.title, Chunk.locator, DocumentVersion.version_label,
                   DocumentVersion.effective_from)
            .join(Chunk, Chunk.id == Citation.chunk_id)
            .join(DocumentVersion, DocumentVersion.id == Citation.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Citation.qa_item_id == item.id).order_by(Citation.rank)
        ).all()
        sources = "\n".join(
            f"{r.label[1:]}. {r.title}｜{r.locator}｜{r.version_label}（{r.effective_from} 生效）" for r in rows
        )
        body = f"【AI 初步參考】\n{item.answer_text}\n\n出處：\n{sources}\n\n查看原文：{liff_url('answers/' + qa)}"
        quick = [
            {"type": "postback", "label": "送交督導確認", "data": f"action=escalate&qa={qa}", "displayText": "送交督導確認"},
            {"type": "postback", "label": "回答有誤", "data": f"action=wrong&qa={qa}", "displayText": "回答有誤"},
            {"type": "postback", "label": "播放語音", "data": f"action=tts&qa={qa}", "displayText": "播放語音"},
        ]
        return [_text(body, quick)]
    if item.outcome == "clarify":
        return [_text(item.answer_text or "可以再說具體一點嗎？")]
    if item.outcome == "escalated" and case is not None:
        return [_text(f"{item.answer_text}\n已送交督導確認（案件 {case.number}）。督導回覆後會通知您。")]
    return [_text(
        f"{item.answer_text}\n⚠ 送交督導失敗：{item.case_error or '請稍後再試'}",
        [{"type": "postback", "label": "重試送交", "data": f"action=retry_case&qa={qa}", "displayText": "重試送交"}],
    )]


def transcript_ready_messages(transcript: Transcript) -> list[dict[str, Any]]:
    """語音轉文字完成後給使用者確認的訊息（顯示遮罩後文字）。"""
    from app.services.deid import deidentify

    segments = transcripts.read_draft(transcript)
    joined = "".join(s["text"] for s in segments)
    masked = deidentify(joined).text
    uncertain = any(s.get("uncertain") for s in segments)
    note = "\n（部分內容辨識信心較低，請確認）" if uncertain else ""
    return [_text(
        f"語音轉文字結果（已遮罩個資）：\n「{masked[:800]}」{note}\n內容正確就按「用這段提問」；要修改請按「修改後再問」。",
        [
            {"type": "postback", "label": "用這段提問", "data": f"action=ask_tr&t={transcript.id}", "displayText": "用這段提問"},
            {"type": "uri", "label": "修改後再問", "uri": liff_url(f"record/{transcript.id}")},
        ],
    )]


def process_event(session: Session, line_event_id: uuid.UUID) -> None:
    """處理一筆 LINE 事件（worker 呼叫；冪等）。"""
    event = session.get(LineEvent, line_event_id)
    if event is None or event.status in {"done", "ignored"}:
        return
    content = decrypt_json(event.payload_encrypted) if event.payload_encrypted else {}
    user = _user_for(session, event.line_user_id)
    path = "none"
    if event.event_type == "follow":
        path = _on_follow(session, event, user)
    elif event.event_type == "unfollow":
        _on_unfollow(session, event)
        path = "state_only"
    elif user is None and event.event_type in {"message", "postback"}:
        if event.reply_token:
            get_line_client(session).reply(event.reply_token, [_text(
                f"尚未綁定帳號。請開啟以下連結，輸入督導給您的綁定碼：{liff_url('bind')}")])
        path = "unbound"
    elif event.event_type == "message" and event.message_type == "text":
        path = _on_text(session, event, user, content.get("text", ""))
    elif event.event_type == "message" and event.message_type == "audio":
        path = _on_audio(session, event, user)
    elif event.event_type == "postback":
        path = _on_postback(session, event, user, content.get("data", ""))
    else:
        path = "ignored"
    event.status = "done" if path != "ignored" else "ignored"
    event.error = path
    event.payload_encrypted = None  # 處理完即清除文字內容
    event.reply_token = None
    event.processed_at = jobs.utcnow()


def _on_follow(session: Session, event: LineEvent, user: User | None) -> str:
    account = session.scalar(select(LineAccount).where(LineAccount.line_user_id == event.line_user_id))
    if account:
        account.is_blocked = False
        account.followed_at = jobs.utcnow()
    if event.reply_token:
        greeting = "歡迎使用長照 AI 照護小幫手（MVP）。"
        if user is None:
            greeting += f"\n請先開啟以下連結完成帳號綁定：{liff_url('bind')}"
        get_line_client(session).reply(event.reply_token, [_text(f"{greeting}\n{PRIVACY_HINT}")])
    return "reply"


def _on_unfollow(session: Session, event: LineEvent) -> None:
    account = session.scalar(select(LineAccount).where(LineAccount.line_user_id == event.line_user_id))
    if account:
        account.is_blocked = True
        account.blocked_at = jobs.utcnow()
        audit.record(session, "line.unfollow", org_id=None, target_type="line_account", target_id=account.id)


def _function_menu() -> dict[str, Any]:
    """One Flex card (desktop fallback) with mobile quick replies; no client sniffing."""
    pages = (("問 AI", "ask"), ("錄音／談話", "record"), ("問題分類", "report"),
             ("我的案件", "cases"), ("使用說明", "help"))
    unavailable = _text("小照｜功能選單\n功能連結暫時無法使用，請聯絡督導協助。")
    base = get_settings().public_base_url
    try:
        parsed = urlsplit(base)
        host = parsed.hostname or ""
        labels = host.encode("idna").decode("ascii").split(".")
        if (parsed.scheme != "https" or not host or "." not in host or len(host) > 253
                or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
                       or not all(c.isascii() and (c.isalnum() or c == "-") for c in label)
                       for label in labels)
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")
                or any(c.isspace() or ord(c) < 32 for c in base)
                or any(c in base for c in "\\%") or parsed.port not in (None, 443)
                or host.lower().endswith((".localhost", ".local", ".internal"))):
            return unavailable
        try:
            if not ipaddress.ip_address(host).is_global:
                return unavailable
        except ValueError:
            pass  # DNS host; no network lookup is needed to build a menu.
        links = [liff_url(page) for _, page in pages]
        if any(link != f"{base.rstrip('/')}/liff/{page}" or len(link) > 1000
               for link, (_, page) in zip(links, pages)):
            return unavailable
    except (TypeError, ValueError, UnicodeError):
        return unavailable
    actions = [{"type": "uri", "label": label, "uri": link}
               for (label, _), link in zip(pages, links)]
    return {
        "type": "flex",
        "altText": "小照｜功能選單\n請點選下方按鈕使用功能。",
        "contents": {
            "type": "bubble",
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                {"type": "text", "text": "小照｜功能選單", "weight": "bold", "size": "lg"},
                {"type": "text", "text": "請點選下方按鈕使用功能。", "wrap": True, "size": "sm"},
            ]},
            "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                {"type": "button", "style": "primary", "color": "#263238",
                 "height": "sm", "action": dict(action)} for action in actions
            ]},
        },
        "quickReply": {"items": [{"type": "action", "action": dict(action)} for action in actions]},
    }


def _on_text(session: Session, event: LineEvent, user: User, message: str) -> str:
    keyword = message.strip()
    if keyword in {"選單", "功能", "幫助"}:
        if event.reply_token:
            get_line_client(session).reply(event.reply_token, [_function_menu()])
        return "menu"
    if keyword in MENU_KEYWORDS:
        page, label = MENU_KEYWORDS[keyword]
        if event.reply_token:
            get_line_client(session).reply(event.reply_token, [_text(f"{label}：{liff_url(page)}")])
        return "menu"
    if strip_wake_word(keyword).greeting_only:  # 「小照你好」：打招呼＋提示怎麼問
        if event.reply_token:
            get_line_client(session).reply(event.reply_token, [_text(greeting_reply(), [
                {"type": "uri", "label": "問 AI", "uri": liff_url("ask")},
                {"type": "uri", "label": "錄音／談話紀錄", "uri": liff_url("record")},
                {"type": "uri", "label": "使用說明", "uri": liff_url("help")},
            ])])
        return "greeting"
    try:
        item, case, _ = qa_service.ask(session, user, question=message, source="line_text",
                                       client_request_id=f"line:{event.webhook_event_id}")
    except qa_service.QaError as exc:
        if event.reply_token:
            get_line_client(session).reply(event.reply_token, [_text(str(exc))])
        return "invalid"
    return _respond(session, event, user, answer_messages(session, item, case), "answer", item.id)


def _on_audio(session: Session, event: LineEvent, user: User) -> str:
    client = get_line_client(session)
    if event.content_provider != "line" or not event.message_id:
        # 外部來源的內容不下載（防 SSRF）
        if event.reply_token:
            client.reply(event.reply_token, [_text("這則語音不是由 LINE 託管，系統不下載外部連結。請直接用 LINE 錄音傳送。")])
        return "external_content_refused"
    try:
        data = client.get_content(event.message_id)
        transcript, _ = transcripts.create_upload(
            session, user, data=data, mode="question", client_upload_id=f"line:{event.message_id}",
            consent_confirmed=False, channel="line", line_message_id=event.message_id,
        )
    except (ContentUnavailable, transcripts.TranscriptError) as exc:
        if event.reply_token:
            client.reply(event.reply_token, [_text(f"語音無法處理：{exc}")])
        return f"audio_error:{getattr(exc, 'code', 'unknown')}"
    if event.reply_token:
        client.reply(event.reply_token, [_text("已收到語音，正在轉成文字，完成後會傳給您確認。")])
        event.reply_token = None
    return f"stt_queued:{transcript.id}"


def notify_transcript_ready(session: Session, transcript: Transcript) -> None:
    """LINE 語音轉錄完成後推播確認訊息（worker 在 STT 成功後呼叫）。"""
    if transcript.channel != "line" or transcript.status != "draft":
        return
    notification = NotificationJob(
        org_id=transcript.org_id, recipient_id=transcript.user_id, source_type="transcript",
        source_id=transcript.id, channel="line", status="queued",
        payload={"kind": "transcript_ready", "messages": transcript_ready_messages(transcript)},
    )
    session.add(notification)
    session.flush()
    jobs.enqueue(session, "notify", {"notification_id": str(notification.id)}, f"notify:{notification.id}")


def _on_postback(session: Session, event: LineEvent, user: User, data: str) -> str:
    params = {k: v[0] for k, v in parse_qs(data).items()}
    action = params.get("action")
    client_request_id = f"line:{event.webhook_event_id}"
    if action == "ask_tr":
        transcript = _owned(session, Transcript, params.get("t"), user)
        if transcript is None:
            return "not_found"
        if transcript.status == "draft":
            segments = transcripts.read_draft(transcript)
            transcripts.confirm(session, user, transcript, edits=[], roles={},
                                selected_idx=[s["idx"] for s in segments], summary=None)
        question = "".join(s.text_masked for s in _segments(session, transcript.id))
        item, case, _ = qa_service.ask(session, user, question=question, source="line_voice",
                                       client_request_id=client_request_id, transcript_id=transcript.id)
        return _respond(session, event, user, answer_messages(session, item, case), "answer", item.id)
    item = _owned(session, QaItem, params.get("qa"), user)
    if item is None:
        return "not_found"
    if action == "escalate":
        try:
            case = qa_service.manual_escalate(session, user, item, "", client_request_id)
            reply = _text(f"已送交督導確認（案件 {case.number}）。")
        except (CaseError, Exception) as exc:  # 建案失敗照實回報（savepoint 已回滾，外層交易不受影響）
            reply = _text(f"送交失敗（{type(exc).__name__}），請稍後再按一次「送交督導確認」。")
        return _respond(session, event, user, [reply], "answer", uuid.uuid5(item.id, client_request_id))
    if action == "retry_case":
        case = qa_service.retry_escalation(session, user, item)
        msg = f"已送交督導確認（案件 {case.number}）。" if case else "仍無法送交督導，請改用 LIFF「我的案件」或直接聯絡督導。"
        return _respond(session, event, user, [_text(msg)], "answer", uuid.uuid5(item.id, client_request_id))
    if action == "wrong":
        exists = session.scalar(select(Feedback).where(Feedback.qa_item_id == item.id, Feedback.user_id == user.id,
                                                       Feedback.kind == "wrong"))
        if exists is None:
            session.add(Feedback(org_id=user.org_id, qa_item_id=item.id, user_id=user.id, kind="wrong"))
            audit.record(session, "qa.feedback", actor=user, target_type="qa_item", target_id=item.id,
                         meta={"kind": "wrong"})
        return _respond(session, event, user, [_text("已記錄「回答有誤」，督導會檢視。需要督導處理請按「送交督導確認」。")],
                        "answer", uuid.uuid5(item.id, client_request_id))
    if action == "tts":
        asset = tts_service.request_tts(session, user, item)
        jobs.enqueue(session, "tts_push", {"asset_id": str(asset.id), "user_id": str(user.id)},
                     f"tts_push:{asset.id}:{event.webhook_event_id}", delay_sec=2, max_attempts=8)
        return _respond(session, event, user, [_text("語音產生中，完成後會傳給您。")], "answer",
                        uuid.uuid5(item.id, client_request_id))
    return "ignored"


def _owned(session: Session, model: Any, raw_id: str | None, user: User) -> Any:
    try:
        obj = session.get(model, uuid.UUID(raw_id or ""))
    except ValueError:
        return None
    if obj is None or obj.user_id != user.id:
        audit.record(session, "access_denied", actor=user, target_type=model.__tablename__, target_id=raw_id,
                     outcome="denied", meta={"via": "line_postback"})
        return None
    return obj


def _segments(session: Session, transcript_id: uuid.UUID) -> list[Any]:
    from app.models import TranscriptSegment

    return list(session.scalars(select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript_id)
                                .order_by(TranscriptSegment.idx)))


def push_tts_audio(session: Session, asset_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """TTS 完成後推播音訊訊息；未完成回傳 False 讓工作稍後重試。LINE 播放須 HTTPS URL。"""
    from app.models import TtsAsset

    asset = session.get(TtsAsset, asset_id)
    user = session.get(User, user_id)
    if asset is None or user is None:
        return True
    if asset.status in {"queued", "running"}:
        return False
    if asset.status != "ready":
        messages = [_text("語音產生失敗，請直接閱讀文字回答。")]
    else:
        url = tts_service.media_url(asset)
        if url and url.startswith("https://"):
            messages = [{"type": "audio", "originalContentUrl": url, "duration": asset.duration_ms or 1000}]
        else:
            messages = [_text(f"語音已產生，請在此播放：{liff_url('answers/' + str(asset.qa_item_id))}")]
    exists = session.scalar(select(NotificationJob.id).where(NotificationJob.source_type == "tts",
                                                             NotificationJob.source_id == asset.id))
    if exists:
        return True
    notification = NotificationJob(org_id=user.org_id, recipient_id=user.id, source_type="tts", source_id=asset.id,
                                   channel="line", status="queued", payload={"kind": "answer", "messages": messages})
    session.add(notification)
    session.flush()
    jobs.enqueue(session, "notify", {"notification_id": str(notification.id)}, f"notify:{notification.id}")
    return True


def build_simulated_event(kind: str, line_user_id: str, *, text_value: str | None = None,
                          message_id: str | None = None, postback: str | None = None) -> dict[str, Any]:
    """組出與官方格式相同的模擬事件（僅 mock 模式使用）。"""
    event: dict[str, Any] = {
        "type": {"text": "message", "audio": "message"}.get(kind, kind),
        "mode": "active",
        "timestamp": int(time.time() * 1000),
        "source": {"type": "user", "userId": line_user_id},
        "webhookEventId": "SIM" + uuid.uuid4().hex[:23].upper(),
        "deliveryContext": {"isRedelivery": False},
        "replyToken": uuid.uuid4().hex,
    }
    if kind == "text":
        event["message"] = {"id": str(int(time.time() * 1e6)), "type": "text", "text": text_value or ""}
    elif kind == "audio":
        event["message"] = {"id": message_id, "type": "audio", "duration": 5000,
                            "contentProvider": {"type": "line"}}
    elif kind == "postback":
        event["postback"] = {"data": postback or ""}
    elif kind == "unfollow":
        event.pop("replyToken")
    return {"destination": "SIMULATED", "events": [event]}


def dumps(payload: dict[str, Any]) -> bytes:
    """以緊湊格式序列化 webhook body（簽章以此 bytes 計算）。"""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def cleanup_payloads(session: Session) -> int:
    """清除已處理或超過一天的事件文字內容與 reply token。"""
    result = session.execute(text(
        "UPDATE line_events SET payload_encrypted = NULL, reply_token = NULL "
        "WHERE (payload_encrypted IS NOT NULL OR reply_token IS NOT NULL) "
        "AND (status IN ('done','ignored') OR received_at < now() - interval '1 day')"
    ))
    return result.rowcount or 0


def settings_summary() -> dict[str, Any]:
    """LINE 設定摘要（不含任何密鑰）。"""
    settings = get_settings()
    return {"mode": settings.line_mode, "liff_id_set": bool(settings.liff_id),
            "login_channel_set": bool(settings.line_login_channel_id)}
