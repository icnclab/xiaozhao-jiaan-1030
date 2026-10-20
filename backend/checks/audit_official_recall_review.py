"""Offline official-source comparison/signoff preparation. No app/DB/search imports."""
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "quality_tests/recall_round1/evidence_review"
OUT = REVIEW / "official_review_20261016"
VERIFIED = "官方來源已核對，待人工核准"
UNCERTAIN = "官方版本仍有疑問"
MISSING = "必要事實缺少可靠證據"
INAPPLICABLE = "不適用居家服務"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def norm(text):
    return re.sub(r"\s+", "", text)


class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden -= 1

    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)


def html_text(path):
    parser = Text(); parser.feed(path.read_text(encoding="utf-8-sig"))
    return "\n".join(parser.parts)


def body_column(page):
    """Only the combination-content column of the visually inspected annex tables.
    Coordinates are intentionally source-specific, never used by production ingestion.
    """
    parts = []
    def visitor(text, cm, tm, font, size):
        if 170 <= tm[4] < 405:
            parts.append(text)
    page.extract_text(visitor_text=visitor)
    return norm("".join(parts))


def ba16_points(text):
    text = norm(text)
    start = text.index("一、目的物品或事項包括：")
    text = text[start:]
    stop = "超過五公里所需費用由長照給付對象自行負擔。"
    text = text[:text.index(stop) + len(stop)]
    markers = ["一、", "二、", "三、", "四、"]
    offsets = [text.index(m) for m in markers] + [len(text)]
    return [text[offsets[n]:offsets[n+1]] for n in range(4)]


def eligible(case):
    # Official-source verification never substitutes for human approval.
    return bool(case.get("human_approved") is True and case.get("reviewer") and
                case.get("signed_at") and case.get("service_date") and
                case.get("necessity_review_complete") is True and
                case.get("local_applicability_confirmed") is True)


def short_form(packet):
    lines = ["# 小照6題證據簽核簡表", "", "官方來源核對不是人工核准。全部尚未核准；五題集中BA16，不代表廣泛知識庫測試。完整原文與逐項勾選見[詳細審核表](signoff.md)。", "",
        "版本A：《長期照顧服務申請及給付辦法》114-06-19修正版及114-10-03勘誤之附表四；本機BA16四點與官方相同。官方PDF14–15頁（未見印刷頁碼），本機PDF14頁。本修正版一般2025-09-01施行，BA16未修正；不是BA16首次生效日。", "",
        "版本B：衛福部《居家服務督導員工作手冊》114年12月初版；官方2026-05-29上架、06-04更新；本機與官方整檔一致。屬工作指引，沒有獨立法規式生效日；PDF與印刷75、111–112頁相同。", "",
        "服務日期：________　所在地／機構：________　覆核人：________", "",
        "| 題目原文 | 必要事實候選／官方定位 | 簽核決定與備註 |", "|---|---|---|"]
    for c in packet["cases"]:
        summary = "；".join(f["draft_fact"] for f in c["draft_necessary_facts"])
        loc = "B，第111頁表前正文；紀錄及分級另查111–112頁與第16條（不是通報期限）" if c["display_id"] == "Q5" else "A，BA16第一／三／四點，依本題所需勾選"
        gap = "；仍缺完整責任／地方流程確認" if c["unresolved_claims"] else ""
        lines.append(f"| {c['display_id']} {c['question']} | {summary}<br>{loc}{gap} | □核准標註　□補件　□不適用<br>必要事實刪補：______<br>簽名／日期：______ |")
    lines += ["", "共同確認：□服務日期及版本適用　□居家／地方流程適用　□必要事實已審閱　□不自行推導選藥／劑量／診斷或通報期限", "",
        "若未核准，原因：□官方版本仍有疑問　□必要事實缺少可靠證據　□不適用居家服務。核心官方來源已核對者，仍維持『待人工核准』直到簽名。", "",
        "督導總簽名：________　共同確認人：________　日期：________", "",
        "本機附表整本同版性未確認；1150305補充函原件未取得；2025-09-01以前服務另查當時原附件。沒有簽核前，正式召回率可計分題數仍為0。"]
    return "\n".join(lines)+"\n"


def main():
    if (OUT / "official_review_packet.json").exists():
        raise SystemExit("Refusing to overwrite the official review packet")
    protected = [ROOT / "quality_tests/recall_round1" / name for name in
                 ("dataset.json", "annotations.json", "observations.json", "baseline_report.json")]
    protected += [ROOT / "quality_tests/v1" / name for name in ("gold_dataset_v1.json", "manifest.json")]
    protected += [p for p in REVIEW.rglob("*") if p.is_file() and OUT not in p.parents]
    before = {p.relative_to(ROOT).as_posix(): sha(p) for p in protected}
    old = read(REVIEW / "review_packet.json")
    captures = read(OUT / "official_sources.json")
    if (OUT / "official_sources_supplement.json").exists():
        captures.update(read(OUT / "official_sources_supplement.json"))
    sources = OUT / "sources"
    for name, info in captures.items():
        if info["status"] == "downloaded" and sha(sources/name) != info["sha256"]:
            raise ValueError("Captured source changed: " + name)
    texts = {name: html_text(sources/name) for name in captures
             if name.endswith(".html") and captures[name]["status"] == "downloaded"}
    pdfs = {name: PdfReader(sources/name) for name in captures
            if name.endswith(".pdf") and captures[name]["status"] == "downloaded"}
    local_annex = PdfReader(ROOT / old["source_documents"]["D1"]["local_path"])
    local_manual = ROOT / old["source_documents"]["D2"]["local_path"]
    official_annex = pdfs["annex4_current.pdf"]
    local_points = ba16_points(body_column(local_annex.pages[13]))
    official_points = ba16_points(body_column(official_annex.pages[13]) + body_column(official_annex.pages[14]))
    if local_points != official_points:
        raise ValueError("BA16 wording differs; manual investigation required")
    if sha(local_manual) != captures["manual_official.pdf"]["sha256"]:
        raise ValueError("Handbook bytes differ; manual investigation required")
    current = norm(texts["law_current.html"])
    history = norm(texts["law_history.html"])
    assert "1141962704" in history and "1141961114" in history
    assert "114年06月19日" in current
    assert "自一百十四年九月一日施行" in current
    assert "BA08、BA09、BA09a" in current
    correction = "\n".join(p.extract_text() or "" for p in pdfs["correction_20251003.pdf"].pages)
    assert "BA16" not in correction
    assert all(code in correction for code in ("BA08", "BD03"))
    comparison = norm(pdfs["amendment_comparison_20250619.pdf"].pages[38].extract_text())
    assert "BA16" in comparison and "本照顧組合未修正" in comparison
    manual = pdfs["manual_official.pdf"]
    assert "114年12月初版" in norm(manual.pages[175].extract_text())
    assert "115-05-29" in texts["manual_landing.html"] and "115-06-04" in texts["manual_landing.html"]
    record_quote = old["evidence_catalog"]["E13"]["quote"]
    assert record_quote in current

    official_evidence = {}
    for n, (left, right) in enumerate(zip(local_points, official_points), 1):
        official_evidence[f"BA16-{n}"] = {
            "quote": right, "kind": "法規附表", "status": VERIFIED,
            "official_file": "sources/annex4_current.pdf", "official_url": captures["annex4_current.pdf"]["url"],
            "official_pdf_pages": [14, 15] if n == 1 else [15], "original_printed_pages": None,
            "page_note": "附表該處未見印刷頁碼；使用PDF檔案頁序。",
            "local_pdf_pages": [14], "comparison": "僅移除排版空白後逐字一致；不含BA15及價格欄",
            "version": "114年6月19日修正發布；併查114年10月3日勘誤；以本次官方附件SHA256識別",
            "version_regime_from": "2025-09-01", "first_ever_ba16_effective_date": None,
            "date_note": "2025-09-01是本次修正版一般施行日，不是BA16首次生效日；對照表明列BA16未修正。歷史服務日期另查。"}
    for eid in ("E05", "E06", "E07", "E08", "E09", "E15"):
        e = old["evidence_catalog"][eid]
        assert e["quote"] in norm(manual.pages[e["pdf_page"]-1].extract_text())
        official_evidence[eid] = dict(e, kind="官方督導工作指引；非獨立法規", status=VERIFIED,
            official_file="sources/manual_official.pdf", official_url=captures["manual_official.pdf"]["url"],
            official_pdf_pages=[e["pdf_page"]], original_printed_pages=[e["pdf_page"]],
            version="114年12月初版；官方網頁115-05-29建檔、115-06-04更新；本機與官方PDF整檔SHA256相同",
            formal_effective_date=None, date_note="出版／上架／更新日期不等於法律生效日；不得溯及假設所有歷史服務均適用。")
    official_evidence["LAW16"] = {"quote": record_quote, "kind": "法規本文", "status": VERIFIED,
        "official_url": captures["law_current.html"]["url"], "official_file": "sources/law_current.html",
        "locator": "第16條末項", "official_pdf_pages": [3], "pdf_alternative": "sources/amendment_combined_20250619.pdf",
        "original_printed_pages": None, "formal_effective_date": "2025-09-01",
        "scope_note": "主體是長照特約單位的一般服務紀錄義務，沒有規定所有異常事件的通報期限。"}

    # Narrow candidate facts, retaining the previous draft and an explicit omission rationale.
    plans = [
        [("藥品列在BA16目的物品內。", "BA16-1"), ("物品原則為給付對象本身所需。", "BA16-3")],
        [("BA16代購／代領／代送服務的目的物品包含藥品。", "BA16-1"), ("物品原則為給付對象本身所需。", "BA16-3")],
        [("自案家出門起算五公里內適用本組合。", "BA16-4"), ("超過五公里所需費用由給付對象自行負擔；不是絕對禁止超過五公里。", "BA16-4")],
        [("物品原則為給付對象本身所需。", "BA16-3"), ("包含給付對象以外家人物品時，組合金額僅支付百分之五十。", "BA16-3"), ("包含給付對象以外家人物品時，另外百分之五十由給付對象自行負擔。", "BA16-3")],
        [("第一線服務人員發現異常事件應立即報告單位主管。", "E05"), ("說明事情發生經過。", "E05"), ("不得無故延遲回報。", "E05")],
        [("藥品列在BA16目的物品內。", "BA16-1"), ("物品原則為給付對象本身所需。", "BA16-3"), ("包含給付對象以外家人物品時，組合金額僅支付百分之五十。", "BA16-3"), ("包含給付對象以外家人物品時，另外百分之五十由給付對象自行負擔。", "BA16-3"), ("自案家出門起算五公里內適用本組合。", "BA16-4"), ("超過五公里所需費用由給付對象自行負擔。", "BA16-4")]
    ]
    cases = []
    for previous, plan in zip(old["cases"], plans):
        q = previous["display_id"]
        facts = [{"id": q+f"-C{n}", "draft_fact": text, "evidence_id": eid,
                  "evidence_status": VERIFIED, "necessity_status": "待人工確認", "human_approved": False}
                 for n, (text, eid) in enumerate(plan, 1)]
        supplemental = ["BA16-2", "BA16-3", "BA16-4"] if q in ("Q1", "Q2") else []
        if q == "Q5": supplemental = ["E06", "E07", "E08", "LAW16", "E15"]
        missing = []
        if q in ("Q1", "Q2", "Q6"):
            missing = [{"claim": "舊答案中自行選藥、劑量、服法及醫療專業確認的完整責任界線", "status": MISSING,
                        "note": "E09只支持私自給藥／越權處置的指引；不補造完整醫療法規。必要性待督導決定。"}]
            supplemental.append("E09")
        if q == "Q5":
            missing = [{"claim": "個案分級、通報對象／期限、診斷責任及機構內紀錄分工", "status": MISSING,
                        "note": "沒有個案嚴重度、所在地主管機關規範與機構SOP；不得從第16條推導通報時限。"}]
        cases.append({"case_id": previous["case_id"], "display_id": q, "question": previous["question"],
            "origin": previous["origin"], "evidence_status": VERIFIED, "draft_necessary_facts": facts,
            "previous_draft_preserved_at": "../review_packet.json", "previous_fact_ids": [f["id"] for f in previous["draft_facts"]],
            "revision_note": "僅按問題範圍提出較精簡候選；未刪除舊草稿，未替人工決定必要事實或核准答案。",
            "supplementary_evidence_ids": list(dict.fromkeys(supplemental)), "unresolved_claims": missing,
            "source_kind": "工作指引及一般服務紀錄法規" if q == "Q5" else "法規附表BA16",
            "home_care": "來源範圍支持居家；實際給付資格、所在地及機構分工待督導確認",
            "service_date": None, "service_location": None, "reviewer": None, "signed_at": None,
            "human_approved": False, "necessity_review_complete": False, "local_applicability_confirmed": False,
            "reviewer_notes": "", "eligible_for_formal_recall": False})

    packet = {"schema_version": 1, "checked_for_client_date": "2026-10-16", "prior_review_sha256": sha(REVIEW/"review_packet.json"),
        "status_vocabulary": [VERIFIED, UNCERTAIN, MISSING, INAPPLICABLE], "cases": cases,
        "official_evidence": official_evidence, "official_source_capture": "official_sources.json",
        "local_full_annex_version_status": UNCERTAIN,
        "local_full_annex_note": "本機51頁與官方53頁整檔不同；只確認本輪BA16四點一致，不宣稱整本同版或替換知識庫。",
        "coverage_limit": "6題中5題集中BA16、1題事件通報；不是廣泛長照知識庫測試。",
        "new_notice_caution": {"landing": captures["ba16_notice_landing.html"]["url"],
            "document_number": "115年3月5日衛部顧字第1151960640號函", "source_kind": "地方政府轉載中央函釋",
            "original_pdf_download_status": captures.get("ba16_notice_20260305.pdf", {}).get("status", "not_attempted"),
            "status": UNCERTAIN, "note": "官方轉載頁已核對，原函PDF未成功取得；在宅領受、關懷及異常通報之補充必要性與地方適用待督導核對，不自動加入標準答案。"},
        "formal_recall_eligible": 0, "human_approved": 0, "recall_rates": None,
        "historical_date_caution": "2025修正版一般施行日不等於BA16首次施行日；2025-09-01以前服務須另取當時有效原始附件。手冊也不得直接溯用。"}
    comparison_report = {"local_annex_pages": len(local_annex.pages), "official_annex_pages": len(official_annex.pages),
        "whole_annex_sha256_equal": sha(ROOT/old["source_documents"]["D1"]["local_path"]) == captures["annex4_current.pdf"]["sha256"],
        "ba16_point_matches": [a == b for a,b in zip(local_points, official_points)],
        "local_ba16_page": 14, "official_ba16_pages": [14,15], "manual_whole_sha256_equal": True,
        "manual_checked_pages": [75,111,112], "amendment_comparison_ba16_pages": [39,40],
        "correction_pdf_pages": 7, "correction_annex4_pages": [4,5,6], "correction_contains_ba16": False,
        "legal_regime_general_effective_date": "2025-09-01", "ba16_changed_in_20250619_comparison": False,
        "not_asserted": ["first ever BA16 effective date", "all historical dates applicable", "all local annex pages current", "no later unpublished changes"]}
    (OUT/"official_review_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT/"comparisons.json").write_text(json.dumps(comparison_report, ensure_ascii=False, indent=2), encoding="utf-8")
    extracts = {name: {str(n): pdfs[name].pages[n-1].extract_text() or "" for n in nums}
                for name, nums in {"annex4_current.pdf": [14,15], "manual_official.pdf": [4,75,111,112,176],
                    "amendment_comparison_20250619.pdf": [39,40], "amendment_combined_20250619.pdf": [3,4],
                    "correction_20251003.pdf": list(range(1,8))}.items()}
    (OUT/"official_extracts.json").write_text(json.dumps(extracts, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 小照第4步：人工勾選與簽核表", "", "官方核對完成不等於督導核准。6題目前皆未核准，正式召回率測試資格0題；不填造分數。", "",
        "五題集中BA16、一題通報，不能宣稱已廣泛測試長照知識庫。題目維持原文，舊候選資料保留在上一層。", "",
        "## 版本、日期及頁碼", "",
        "| 文件 | 核對結果 | 日期與效力 |", "|---|---|---|",
        "| 長期照顧服務申請及給付辦法／附表四 | 官方53頁，本機51頁；BA16四點排版空白正規化後逐字一致。官方PDF14–15頁，本機PDF14頁；該處未見印刷頁碼。 | 114-06-19衛部顧字第1141961114號令；114-10-03衛部顧字第1141962704號函勘誤。本修正版一般自2025-09-01施行，BA16不在延後項目；對照表39–40頁列BA16未修正，不能說BA16是當日新規。歷史服務另核。 |",
        "| 居家服務督導員工作手冊 | 官方與本機PDF整檔SHA256相同；75、111、112頁的PDF頁序與印刷頁碼相同。176頁為114年12月初版。 | 官方網頁2026-05-29上架、2026-06-04更新，均不是法規生效日。屬工作參考指引；不替代最新法令及地方流程。 |",
        "| 第16條 | 官方本文末項與本機引文一致；修正條文合併PDF第3頁。 | 一般服務紀錄義務，不是所有異常事件的通報期限。 |", "",
        "[現行法規](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070059)／[沿革與勘誤](https://law.moj.gov.tw/LawClass/LawHistory.aspx?pcode=L0070059)／[手冊官方頁](https://1966.gov.tw/LTC/cp-7565-86698-207.html)", "",
        "官方版本仍有疑問：本機附表全檔同版性尚未確認；轉載1150305中央函原件未取得。不是BA16四點本身比對失敗。", "",
        "## 逐題簽核（請先填服務日期與所在地）", ""]
    for c in cases:
        lines += [f"### {c['display_id']}　{c['question']}", "", f"來源：`{c['origin']['file']}`／`{c['origin']['record_id']}`。", "",
                  "服務日期：________　機構／所在地：________", "",
                  f"核心證據狀態：{VERIFIED}；居家適用性：{c['home_care']}。", "",
                  "| 事實候選 | 官方定位 | 督導勾選 |", "|---|---|---|"]
        for f in c["draft_necessary_facts"]:
            e = official_evidence[f["evidence_id"]]
            locator = "附表四PDF14–15頁／"+f["evidence_id"] if f["evidence_id"].startswith("BA16") else "手冊PDF及印刷第111頁／表前正文"
            lines.append(f"| {f['id']}：{f['draft_fact']} | {locator}；原文見下方索引 | □必要　□補充　□不採用 |")
        lines += ["", "補充證據（不自動列入分母）：" + ("、".join(c["supplementary_evidence_ids"]) or "由督導依問題範圍補充") + "。"]
        for gap in c["unresolved_claims"]:
            lines += ["", f"{MISSING}：{gap['claim']}。{gap['note']}"]
        lines += ["", "□版本及服務日期適用　□居家／地方規範適用　□必要事實已確認　□仍需補件", "",
                  "□官方來源已核對，待人工核准　□官方版本仍有疑問　□必要事實缺少可靠證據　□不適用居家服務", "",
                  "督導意見／補充依據：________________________________________________", "",
                  "最終決定：□核准本題標註　□退回補件　□不適用（本表不預先勾選）", "",
                  "審核人簽名：________　日期：________　共同確認人：________", ""]
    lines += ["## 官方原文索引", "", "下列引文僅移除排版空白；來源分類與條件須保留。", "",
              "| 編號 | 性質／頁碼 | 原文 |", "|---|---|---|"]
    for eid, e in official_evidence.items():
        lines.append(f"| {eid} | {e['kind']}；PDF頁序{e.get('official_pdf_pages')}；印刷頁碼{e.get('original_printed_pages') or '該處未見／以條號定位'} | {e['quote']} |")
    lines += ["", "## 不得省略的限制", "",
        "- BA15尾段與BA16第一點在同一官方頁，但屬不同表格列；此次按內容欄與BA16項目邊界比對，沒有把BA15納入。",
        "- 勘誤原件7頁已檢查，附表四勘誤4–6頁涵蓋BA08、BD03、F碼通則，未列BA16。這不是對所有歷史變更的無限保證。",
        "- Q1、Q2、Q6不加入自行選藥、劑量或診斷建議。手冊75頁只可支持私自給藥等越權指引，完整責任界線須補可靠依據或由督導決定不列入本題。",
        "- Q5的111頁中度傷害附註與112頁重度等附註不同；未知分級時不指定時限。第16條只作紀錄補充，不替代事件通報SOP。",
        "- 官方轉載另有115年3月5日中央函，涉及BA16在宅領受、關懷與異常通報；原函未成功取得，僅列追查，不自動擴增標準答案。",
        "- 網站法規整編有時間落差；本次頁面截止資訊為115年10月8日，不能保證涵蓋其後尚未整編的公告。", "",
        "## 下一階段", "", "所有題目仍需人員簽核，且須有安全隔離A/B/C快照及快照綁定人工判斷後才計分。這份文件本身不會更新dataset或annotations。"]
    (OUT/"signoff.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    (OUT/"signoff_short.md").write_text(short_form(packet), encoding="utf-8")
    after = {p: sha(ROOT/p) for p in before}
    assert before == after
    assert all(not eligible(c) for c in cases)
    checks = {"ba16_four_points_match": True, "manual_bytes_match": True, "case_questions_unchanged": all(a["question"] == b["question"] for a,b in zip(old["cases"], cases)),
              "human_approved": 0, "formal_recall_eligible": 0, "protected_files_before": before, "protected_files_after": after,
              "network_calls_in_audit": 0, "db_connections": 0, "searches": 0, "model_calls": 0,
              "official_pdf_fetches_successful": sum(k.endswith('.pdf') and v['status']=='downloaded' for k,v in captures.items()),
              "supplement_original_unavailable": captures.get('ba16_notice_20260305.pdf',{}).get('status') != 'downloaded'}
    (OUT/"validation.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in checks.items() if not k.startswith('protected_')}, ensure_ascii=False))


if __name__ == "__main__":
    main()
