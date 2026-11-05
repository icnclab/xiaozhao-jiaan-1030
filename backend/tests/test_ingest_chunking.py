"""最小回歸測試：中文條列（一、二、三、四、）不再被標題辨識覆蓋而遺失原文。

背景：2026-11 嘉安血糖異常示範案例發現，_chunk_paragraphs 把「一、」「二、」等條列
開頭、但本身已是完整句子的內容誤判為標題，導致中間條列項目在切塊時被覆蓋消失。
"""
from app.services.ingest import ParsedDocument, Page, chunk


def _chunk_texts(lines: list[str]) -> list[str]:
    parsed = ParsedDocument(mime="text/plain", pages=[Page(number=None, lines=lines)])
    drafts, warnings = chunk(parsed)
    assert warnings == []
    return [d.text for d in drafts]


class TestListItemsNotLostAsHeadings:
    def test_four_sentence_list_items_all_survive(self):
        lines = [
            "血糖異常記錄與通報內規",
            "飯後血糖偏高但長輩意識清楚、精神狀態正常時，照服員應：",
            "一、記錄當次血糖數值、用餐時間與餐後量測時間差。",
            "二、持續觀察意識、呼吸與膚色等生命徵象變化。",
            "三、如重複偏高或出現意識改變等異常，應依規定通報居督，並建議安排就醫評估。",
            "四、不可由照服員自行調整藥物劑量。",
        ]
        texts = _chunk_texts(lines)
        combined = "\n".join(texts)
        for expected in ("一、記錄當次血糖數值", "二、持續觀察意識", "三、如重複偏高", "四、不可由照服員自行調整藥物劑量"):
            assert expected in combined, f"遺失條列內容：{expected}"

    def test_bracketed_numeral_sentence_items_survive(self):
        lines = [
            "通報流程",
            "（一）發現異常時應立即記錄並通知居督確認後續處理方式。",
            "（二）居督確認後應回覆照服員並留存紀錄備查。",
        ]
        texts = _chunk_texts(lines)
        combined = "\n".join(texts)
        assert "（一）發現異常時應立即記錄並通知居督確認後續處理方式" in combined
        assert "（二）居督確認後應回覆照服員並留存紀錄備查" in combined


class TestRealHeadingsStillRecognized:
    def test_short_label_heading_still_becomes_heading(self):
        lines = ["一、服務範圍", "提供日常生活照顧、身體照顧及家務協助等服務內容。"]
        parsed = ParsedDocument(mime="text/plain", pages=[Page(number=None, lines=lines)])
        drafts, _ = chunk(parsed)
        assert len(drafts) == 1
        assert drafts[0].heading == "一、服務範圍"
        assert "提供日常生活照顧" in drafts[0].text

    def test_chapter_and_section_heading_unaffected(self):
        lines = ["第一章 總則", "本章規範服務對象與適用範圍。", "第二節 服務內容", "本節規範各項服務之具體內容。"]
        parsed = ParsedDocument(mime="text/plain", pages=[Page(number=None, lines=lines)])
        drafts, _ = chunk(parsed)
        headings = [d.heading for d in drafts]
        assert "第一章 總則" in headings
        assert "第二節 服務內容" in headings

    def test_plain_paragraphs_without_markers_unaffected(self):
        lines = ["一般說明段落第一句。", "一般說明段落第二句，內容延續前句。"]
        texts = _chunk_texts(lines)
        assert len(texts) == 1
        assert "一般說明段落第一句" in texts[0]
        assert "一般說明段落第二句" in texts[0]


class TestRegulationArticlesUnaffected:
    def test_article_structure_still_chunks_by_article(self):
        lines = ["第 1 條　本法之目的為規範長照服務。", "第 2 條　本法主管機關為衛生福利部。"]
        parsed = ParsedDocument(mime="text/plain", pages=[Page(number=None, lines=lines)])
        drafts, _ = chunk(parsed)
        assert [d.article_no for d in drafts] == ["第 1 條", "第 2 條"]
        assert "規範長照服務" in drafts[0].text
        assert "衛生福利部" in drafts[1].text
