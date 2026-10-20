"""Prepare pending human evidence review from local files only; never imports app/DB.
Reads PDFs with pypdf. Does not publish documents, approve cases or score recall.
"""
import hashlib
import json
import re
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "quality_tests/recall_round1/evidence_review"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def norm(text):
    return re.sub(r"\s+", "", text)


def section(text, start, end):
    text = norm(text)
    a = text.index(norm(start)); b = text.index(norm(end), a) + len(norm(end))
    return text[a:b]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "review_packet.json").exists():
        raise SystemExit("Refusing to overwrite human review packet")
    protected_paths = [ROOT / p for p in (
        "quality_tests/recall_round1/dataset.json", "quality_tests/recall_round1/annotations.json",
        "quality_tests/recall_round1/observations.json", "quality_tests/recall_round1/baseline_report.json",
        "quality_tests/v1/gold_dataset_v1.json", "quality_tests/v1/manifest.json", "docs/clean-db-manifest.json")]
    protected = {str(p.relative_to(ROOT)): sha(p) for p in protected_paths}
    manifest = read(ROOT / "docs/clean-db-manifest.json")
    definitions = {
        "D1": ("附表四 照顧組合表", "cc0de563-442a-4dde-8877-f9a332e54955", "*.pdf"),
        "D2": ("居家服務督導員工作手冊", "c3304a51-2e5e-42be-b332-cee7aaacf2cb", "*.pdf"),
        "D3": ("長期照顧服務申請及給付辦法", "1e054ebe-0846-495a-a0ff-e842bf0d4f19", "*.txt"),
    }
    sources = {}; pages = {}; documents = {}
    for key, (title, folder, pattern) in definitions.items():
        listed = next(d for d in manifest["approved"] if d["title"] == title)
        files = list((ROOT / "data_clean/documents" / folder).glob(pattern))
        if len(files) != 1:
            raise ValueError("Missing/ambiguous local original: " + title)
        path = files[0]; actual_hash = sha(path)
        if actual_hash != listed["sha256"]:
            raise ValueError("Local original hash differs from manifest: " + title)
        sources[key] = {"title_in_manifest": title, "local_path": str(path.relative_to(ROOT)),
                        "sha256": actual_hash, "manifest_match": True, "manifest_source": listed["source"],
                        "manifest_effective_from_unverified": listed["effective_from"],
                        "file_version_review_status": "待人工確認", "formal_effective_date_confirmed": False}
        if pattern == "*.pdf":
            pdf = PdfReader(path); documents[key] = pdf
            chosen = [1, 14] if key == "D1" else [4, 5, 66, 75, 108, 109, 110, 111, 112, 175, 176]
            pages[key] = {str(n): pdf.pages[n-1].extract_text() or "" for n in chosen}
            sources[key]["pdf_page_count"] = len(pdf.pages)
        else:
            pages[key] = {"text": path.read_text(encoding="utf-8-sig")}
    sources["D1"].update(full_name_in_file="附表四 照顧組合表修正規定",
        version_note="PDF本身未見修正發布日；以SHA256辨識本機內容。歷史系統標籤STUST_clean_20261010_v1不是法規版次。",
        effective_date_note="清單記2026-07-01；本文第22條分項施行，不能直接把此日當BA16生效日。需核對附表與發布令是否同版。",
        applicability_note="BA16案家服務；搭配本文第2、8、9條核對居家給付範圍，非全日住宿式規範。")
    sources["D2"].update(full_name_in_file="居家服務督導員工作手冊",
        edition_in_file="中華民國114年12月初版（2025年12月），PDF第176頁",
        version_note="歷史系統標籤或檔案建立日期不等於出版版次。",
        effective_date_note="清單記2026-05-29，但手冊無法規式生效日；初版日期不能代替生效日。",
        applicability_note="前言第4頁明示居家式長照機構使用；仍以最新法令、所在地主管機關與機構流程為準。")
    sources["D3"].update(full_name_in_file="長期照顧服務申請及給付辦法",
        version_note="匯入用文字版；檔首記民國114年06月19日修正，不是官方發布令影本。",
        effective_date_note="第22條載分項施行；BA16附表是否對應同一修正版仍待確認。",
        applicability_note="第2條排除全日住宿式及團體家屋；第8條含居家照顧服務，第9條連結附表。")

    evidence = {}
    def add(key, doc, page, locator, start, end, note=""):
        raw = pages[doc][str(page)]
        quote = section(raw, start, end)
        evidence[key] = {"document_id": doc, "pdf_page": page if isinstance(page, int) else None,
                         "locator": locator, "quote": quote, "whitespace_only_normalized": True,
                         "scope_note": note, "review_status": "待人工確認"}
    add("E01", "D1", 14, "BA16第一點", "一、目的物品或事項包括：", "繳費）。")
    add("E02", "D1", 14, "BA16第二點", "二、以上服務均含", "完整服務。", "可供督導判斷服務完整範圍；不自動加入每題必要事實。")
    add("E03", "D1", 14, "BA16第三點", "三、上述目的物品或事項", "自行負擔支付。")
    add("E04", "D1", 14, "BA16第四點", "四、本組合以代購", "所需費用由長照給付對象自行負擔。")
    add("E05", "D2", 111, "第四章第二節／肆、二、事件嚴重度與通報時效，表格前正文", "事件發生後，發現異常事件", "不得無故延遲回報。")
    add("E06", "D2", 111, "同節（一）初報／中度傷害列附註", "第一線服務人員應立即報告單位主管，說明事情發生或發現經過", "不得無故延遲回報。", "表格附註位於中度傷害列；不可據未知症狀自行套用事件分級或期限。")
    add("E07", "D2", 112, "同節初報表續頁／重度、極重度及死亡列附註", "第一線服務人員應立即報告單位主管，說明事情發生經過", "完整記錄事發經過。", "與111頁處置文字不同，須保留嚴重度條件。")
    add("E08", "D2", 112, "初報表後／各縣市主管機關要求", "若因以上事件，導致居家服務", "進行異動通報。", "通報者、對象及地方流程須由督導確認；不設通用期限。")
    add("E09", "D2", 75, "第二章／二、服務紀律與時間問題（六）", "（六）違規操作或越權行為", "（如打針）等。", "僅直接支持私自給藥／越權處置界線，不能擴寫成所有選藥、劑量及服法的完整法規。")
    add("E10", "D3", "text", "第2條末段", "全日住宿式服務及團體家屋", "不適用本辦法。")
    add("E11", "D3", "text", "第8條第一項", "前條第二項第一款第一目照顧及專業服務，其內容如下：", "四、專業服務。")
    add("E12", "D3", "text", "第9條第一項", "長照服務給付細項之照顧組合名稱", "規定如附表四及附表四之一。")
    add("E13", "D3", "text", "第16條末段", "長照特約單位應就其提供之長照服務", "供地方主管機關查核。", "義務主體為長照特約單位；照服員實際填表及分工仍需機構流程。")
    add("E14", "D3", "text", "第22條第二項", "本辦法中華民國一百十四年六月十九日修正發布之條文", "自一百十四年九月一日施行。", "分項施行原文；不自動將清單日期轉成BA16的有效日期。")
    add("E15", "D2", 4, "前言末段", "本手冊內容係依編撰時", "最新公告之法令規定為準。")

    dataset = read(ROOT / "quality_tests/recall_round1/dataset.json")
    wanted = [c for c in dataset["cases"] if c["expected_behavior"] not in ("risk_block", "clarify")]
    if len(wanted) != 6:
        raise ValueError("Expected exactly six unchanged knowledge queries")
    # Candidates only: human reviewer decides necessity, applicability and correctness.
    plans = [
        [("藥品列在BA16目的物品內。", "E01"), ("目的物品原則為給付對象本身所需。", "E03"), ("包含其他家人物品時，組合金額僅支付百分之五十。", "E03"), ("另外百分之五十由給付對象自行負擔。", "E03"), ("自案家出門起算五公里內適用本組合。", "E04"), ("超過五公里所需費用由給付對象自行負擔。", "E04")],
        [("BA16代購／代領／代送服務的目的物品包含藥品。", "E01"), ("目的物品原則為給付對象本身所需。", "E03"), ("包含其他家人物品時，組合金額僅支付百分之五十。", "E03"), ("另外百分之五十由給付對象自行負擔。", "E03")],
        [("距離自案家出門起算五公里內適用本組合。", "E04"), ("超過五公里所需費用由給付對象自行負擔；不能改寫成絕對禁止超過五公里。", "E04")],
        [("原則為長照給付對象本身所需。", "E03"), ("包含給付對象以外家人物品時，組合金額僅支付百分之五十。", "E03"), ("另外百分之五十由長照給付對象自行負擔支付。", "E03")],
        [("第一線服務人員發現異常事件，應立即報告單位主管。", "E05"), ("向主管說明事情發生經過。", "E05"), ("現場對服務使用者及家屬即時解說並取得諒解。", "E05"), ("不得無故延遲回報。", "E05"), ("長照特約單位應製作服務紀錄；照服員紀錄分工需機構確認。", "E13")],
        [("BA16目的物品包含藥品。", "E01"), ("目的物品原則應為給付對象本身所需。", "E03"), ("包含其他家人物品時，組合金額僅支付百分之五十。", "E03"), ("另外百分之五十由給付對象自行負擔。", "E03"), ("自案家出門起算五公里內適用本組合。", "E04"), ("超過五公里所需費用由給付對象自行負擔。", "E04")],
    ]
    cases = []
    for index, (original, plan) in enumerate(zip(wanted, plans), 1):
        facts = []
        for n, (text, ref) in enumerate(plan, 1):
            entry = evidence[ref]; doc = sources[entry["document_id"]]
            facts.append({"id": f"Q{index}-F{n}", "draft_fact": text, "evidence_id": ref,
                          "original_quote": entry["quote"], "document": doc["full_name_in_file"],
                          "file_sha256": doc["sha256"], "locator": entry["locator"], "pdf_page": entry["pdf_page"],
                          "necessity": "待人工確認；未核准、未加入正式分母", "review_status": "待人工確認"})
        unresolved = ["確認附表／手冊版本及問題所適用日期。", "確認所在地主管機關與機構現行流程。"]
        supplementary = []
        if index in (1, 2, 6):
            supplementary = ["E09"]
            unresolved.append("舊標準答案的自行選藥、決定劑量／服法及醫療專業確認，不能只用BA16證明；E09僅支持私自給藥界線，完整依據尚未確認。")
        if index == 5:
            supplementary = ["E06", "E07", "E08", "E15"]
            unresolved.append("問題沒有提供嚴重度，不得套用表內特定時限或把中度傷害處理當成所有異常生理狀況；診斷界線的完整依據尚未確認。")
        cases.append({"display_id": f"Q{index}", "case_id": original["id"], "question": original["question"],
                      "origin": original["origin"], "draft_facts": facts, "supplementary_evidence": supplementary,
                      "home_care_applicability": "原文支持居家主題；有效版本與個案給付／地方條件仍待人工確認",
                      "core_original_available": True, "ready_for_final_approval": False,
                      "review_status": "待人工確認", "reviewer": None, "reviewed_at": None,
                      "reviewer_notes": "", "unresolved": unresolved})

    # Keep the exception's condition inside each atomic candidate, not only in the preceding row.
    for case in cases:
        for fact in case["draft_facts"]:
            if fact["draft_fact"].startswith("另外百分之五十"):
                fact["draft_fact"] = "包含給付對象以外家人物品時，" + fact["draft_fact"]

    packet = {"schema_version": 1, "purpose": "pending_human_evidence_review_only",
              "source_documents": sources, "evidence_catalog": evidence, "cases": cases,
              "summary": {"cases": 6, "core_local_original_available": 6, "missing_core_original": 0,
                          "approved": 0, "pending_version_or_effective_date": 6,
                          "old_answer_boundary_claims_need_further_basis": 4},
              "findings": ["No confirmed residential-only rule was used as home-care evidence in these six drafts.",
                           "Historical chunk paragraph 98 includes the end of BA15 and the BA16 heading; do not treat it as BA16 operative terms.",
                           "Importer effective dates and internal labels are not official publication/effective dates.",
                           "Manual page111 note is in the moderate-injury row; page112 has different severe-injury wording."],
              "database_connections": 0, "searches": 0, "model_calls": 0,
              "protected_before_sha256": protected}
    for case, original in zip(cases, wanted):
        assert case["question"] == original["question"]
        assert case["review_status"] == "待人工確認" and case["reviewer"] is None
    for key, entry in evidence.items():
        assert entry["quote"] in norm(pages[entry["document_id"]][str(entry["pdf_page"] or "text")]), key
    for p, value in protected.items():
        assert sha(ROOT/p) == value, p
    for doc in sources.values():
        assert sha(ROOT/doc["local_path"]) == doc["sha256"]
    (OUT / "review_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "extracted_pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 小照：6題正確證據人工審核表", "", "全部為「待人工確認」。原文已從本機PDF／文字檔核對，不代表標準答案已獲核准。沒有修改dataset、annotations、Gold或原始文件。", "",
             "題目原文保留；F為必要事實候選，需由督導確認是否必要。E為下方原文證據編號。中文原文僅移除排版空白，未改動數字與措辭。", "",
             "## 文件與版本", "", "| 文件 | 名稱、版本與日期 | 居家適用性／待辦 |", "|---|---|---|"]
    for key, doc in sources.items():
        lines.append(f"| {key} | {doc['full_name_in_file']}；清單來源名稱：{doc['manifest_source']}；{doc.get('edition_in_file', doc['version_note'])}；清單日期{doc['manifest_effective_from_unverified']}僅供比對 | {doc['effective_date_note']} {doc['applicability_note']} |")
    lines += ["", "本機原始文件（只讀，SHA256均符合正式清單）：", ""]
    for key, doc in sources.items():
        lines.append(f"- [{key}：{doc['full_name_in_file']}](<{(ROOT/doc['local_path']).as_posix()}>)；SHA256 `{doc['sha256']}`")
    lines += ["", "表格預覽：[BA16第14頁](previews/benefits_p14.png)、[手冊第111頁](previews/manual_p111.png)、[第112頁](previews/manual_p112.png)、[版次第176頁](previews/manual_p176.png)。"]
    lines += ["", "D1 PDF第14頁未見印刷頁碼；本表指從檔案第1頁起算。D2所列PDF頁碼與頁腳印刷頁碼相同。D3是匯入文字版，使用條號，不編造頁碼。", "",
              "## 逐題審核", ""]
    for c in cases:
        lines += [f"### {c['display_id']}：{c['question']}", "",
                  f"來源：`{c['origin']['file']}`，原ID `{c['origin']['record_id']}`。", "",
                  "| 必要事實候選 | 原文證據 | 文件與定位 | 居家適用性 | 審核狀態 | 審核人備註 |", "|---|---|---|---|---|---|"]
        for f in c["draft_facts"]:
            e = evidence[f["evidence_id"]]; d = sources[e["document_id"]]
            locator = (f"PDF第{e['pdf_page']}頁／" if e["pdf_page"] else "") + e["locator"]
            lines.append(f"| {f['id']}：{f['draft_fact']} | {f['evidence_id']}：{f['original_quote']} | {e['document_id']} {d['full_name_in_file']}；{locator}；版本見上表 | 主題符合居家；時點及機構條件待確認 | 待人工確認 | ______ |")
        if c["supplementary_evidence"]:
            lines += ["", "補充原文（不得自動列為必備事實）：" + "、".join(c["supplementary_evidence"]) + "，見下表。"]
        lines += ["", "督導確認事項："] + ["- " + x for x in c["unresolved"]] + ["", "審核人：______　日期：______　必要事實／版本／適用性意見：______", ""]
    lines += ["## 原文證據索引", "", "| 編號 | 文件與頁碼／條號 | 原文證據 | 使用限制 |", "|---|---|---|---|"]
    for key, e in evidence.items():
        lines.append(f"| {key} | {e['document_id']}／{('PDF第'+str(e['pdf_page'])+'頁／') if e['pdf_page'] else ''}{e['locator']} | {e['quote']} | {e['scope_note'] or '待人工確認必要性及適用性'} |")
    lines += ["", "## 已發現的風險", "",
              "- 未發現本輪採用住宿式專用規範；D3第2條明確排除全日住宿式及團體家屋，D2第4頁明示居家用途。這不代表已審核整個知識庫沒有混用。",
              "- D1第14頁上半部是前一個BA15項目的尾段，不能把歷史第98段整塊算成BA16證據。BA16證據從碼別列第一點開始。",
              "- D1日期尚須核對發布令；D2第176頁為114年12月初版，不能以匯入清單的2026-05-29當成法律生效日。",
              "- D2第111頁表格的中度傷害附註與112頁重度等附註不同；不以通用的幾小時回答未分級問題。所在地主管機關及機構SOP仍須確認。",
              "- 3題用藥問題的完整選藥／劑量／服法界線及1題診斷界線，不能僅靠本輪核心條文核准；已列缺口，不補造法規。", "",
              "## 交付與下一步", "",
              "6題都有核心原始文件，可供人工審閱；缺少核心本機原始文件0題；核准0題；6題日期／版本仍待確認，4題另有舊答案界線完整性待補。",
              "督導先核對原始文件與適用日期、選定真正必要的原子事實，再簽名。此封包不會自動更新正式required_facts或annotations。",
              "人工確認後另建審核版資料，保留原始基準；再於已證實隔離的環境取得完整A/B/C與實際模型請求，對每個快照綁定SHA256人工標註，才計算可信的修改前召回率。", "",
              "本次未引用新的論文或50篇索引，沿用既有必要事實Context Recall方法。PDF頁面預覽位於previews/；JSON原文與來源SHA256可機器核對。"]
    (OUT / "review_table.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    (OUT / "validation_report.json").write_text(json.dumps({
        "question_verbatim_matches": 6, "pending_without_reviewer": 6,
        "quotes_present_in_original": len(evidence), "local_source_manifest_hash_matches": len(sources),
        "protected_input_hashes_unchanged": protected, "source_hashes_after": {k: sha(ROOT/v['local_path']) for k,v in sources.items()},
        "approved": 0, "database_connections": 0, "searches": 0, "model_calls": 0,
        "limitations": "Mechanical checks and PDF visual inspection only; human approval remains pending."
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(cases), "evidence_quotes_verified": len(evidence), "approved": 0,
                      "protected_files_unchanged": len(protected), "source_files_hash_matched": len(sources)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
