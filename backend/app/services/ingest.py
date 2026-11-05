"""文件解析與切塊。

- 格式以檔頭判斷（`%PDF`、DOCX 的 zip 結構、UTF-8 文字），不看副檔名。
- 有「第 X 條」的文件按條文切；否則按段落切（約 400 字一塊），保留頁碼與段落序。
- 抽不到文字的 PDF 頁（多半是掃描影像）記警告，不自行 OCR 猜內容。
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

MAX_CHUNK_CHARS = 700
TARGET_PARA_CHUNK = 400

_ARTICLE_RE = re.compile(r"^\s*(第\s*[0-9一二三四五六七八九十百零〇]+(?:(?:\s*之\s*|\s*-\s*)[0-9一二三四五六七八九十百零〇]+)?\s*條)\s*(.*)$")
# 結構性標題：markdown 標號或「第…章/節/篇」，文件結構上不會是條列內文本身，一律視為標題。
_STRUCTURAL_HEADING_RE = re.compile(r"^\s*(?:#{1,4}\s+|第[一二三四五六七八九十百零〇]+[章節篇])")
# 條列標記：可能是短標題標籤（如「一、服務範圍」），也可能是條列內文本身已是完整句子
# （如「一、記錄當次血糖數值…。」）。兩者都以同一標記開頭，必須依內容判斷，不能一律當標題。
_LIST_MARKER_RE = re.compile(r"^\s*(?:[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[）)])")
_SENTENCE_END_RE = re.compile(r"[。！？!?；;]\s*$")


def _is_heading_label(stripped: str) -> bool:
    """條列開頭是否為短標籤標題，而非完整條列內文。

    真正的章節標題通常是簡短名詞片語、沒有句尾標點；條列內文若本身已是完整句子
    （以句尾標點結束），代表這一行是實際內容，應保留為內文，否則會被當成標題
    覆蓋掉，使原文遺失（見 2026-11 嘉安血糖示範案例回歸測試）。
    """
    return len(stripped) < 40 and not _SENTENCE_END_RE.search(stripped)


class ParseError(Exception):
    """文件無法解析。"""


@dataclass(frozen=True)
class Page:
    """解析後的一頁（DOCX／文字檔視為單一頁）。"""

    number: int | None
    lines: list[str]


@dataclass
class ParsedDocument:
    """解析結果。"""

    mime: str
    pages: list[Page]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChunkDraft:
    """待寫入的切塊。"""

    seq: int
    locator: str
    article_no: str | None
    page_no: int | None
    heading: str | None
    text: str


def sniff_mime(data: bytes) -> str:
    """依檔頭判斷格式。

    Args:
        data: 檔案內容。

    Returns:
        application/pdf、application/vnd.openxmlformats-officedocument.wordprocessingml.document 或 text/plain。

    Raises:
        ParseError: 不支援的格式。
    """
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except zipfile.BadZipFile as exc:
            raise ParseError("壓縮檔結構損毀") from exc
        raise ParseError("不支援的壓縮格式（只接受 DOCX）")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError("不支援的檔案格式（接受 PDF、DOCX、UTF-8 文字檔）") from exc
    return "text/plain"


def parse(data: bytes) -> ParsedDocument:
    """解析文件成頁與行。

    Args:
        data: 檔案內容。

    Returns:
        解析結果。

    Raises:
        ParseError: 無法解析。
    """
    mime = sniff_mime(data)
    warnings: list[str] = []
    pages: list[Page] = []
    if mime == "application/pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as exc:  # pypdf 會拋多種例外
            raise ParseError("PDF 無法開啟") from exc
        for number, pdf_page in enumerate(reader.pages, start=1):
            text = pdf_page.extract_text() or ""
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                warnings.append(f"第 {number} 頁抽不到文字（可能是掃描影像），未納入檢索")
            pages.append(Page(number=number, lines=lines))
    elif mime.endswith("wordprocessingml.document"):
        import docx

        try:
            document = docx.Document(io.BytesIO(data))
        except Exception as exc:
            raise ParseError("DOCX 無法開啟") from exc
        lines = []
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            if paragraph.style is not None and paragraph.style.name.lower().startswith("heading"):
                text = "# " + text
            lines.append(text)
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    lines.append("｜".join(cells))
        pages.append(Page(number=None, lines=lines))
    else:
        text = data.decode("utf-8").lstrip("﻿")
        pages.append(Page(number=None, lines=[line.rstrip() for line in text.splitlines()]))
    if not any(page.lines for page in pages):
        raise ParseError("文件中沒有可擷取的文字")
    return ParsedDocument(mime=mime, pages=pages, warnings=warnings)


def _split_long(text: str) -> list[str]:
    """把過長文字依句號切成不超過 MAX_CHUNK_CHARS 的片段。"""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    pieces, current = [], ""
    for sentence in re.split(r"(?<=[。；！？])", text):
        if len(current) + len(sentence) > MAX_CHUNK_CHARS and current:
            pieces.append(current)
            current = ""
        current += sentence
    if current:
        pieces.append(current)
    return pieces


def chunk(parsed: ParsedDocument) -> tuple[list[ChunkDraft], list[str]]:
    """切塊：有條文結構就按條，否則按段落。

    Args:
        parsed: 解析結果。

    Returns:
        (切塊清單, 額外警告)。
    """
    flat: list[tuple[int | None, str]] = [(p.number, line) for p in parsed.pages for line in p.lines]
    has_articles = sum(1 for _, line in flat if _ARTICLE_RE.match(line)) >= 2
    return (_chunk_articles(flat) if has_articles else _chunk_paragraphs(flat)), []


def _chunk_articles(flat: list[tuple[int | None, str]]) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    heading: str | None = None
    current_no: str | None = None
    current_page: int | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current_no is None or not buffer:
            return
        body = "".join(buffer).strip()
        for part_index, part in enumerate(_split_long(body)):
            locator = current_no if part_index == 0 else f"{current_no}（續{part_index}）"
            if current_page is not None:
                locator += f"｜第 {current_page} 頁"
            chunks.append(
                ChunkDraft(
                    seq=len(chunks), locator=locator, article_no=current_no, page_no=current_page,
                    heading=heading, text=f"{current_no}　{part}" if part_index == 0 else part,
                )
            )

    for page_no, line in flat:
        match = _ARTICLE_RE.match(line)
        if match:
            flush()
            current_no = re.sub(r"\s+", "", match.group(1)).replace("第", "第 ").replace("條", " 條")
            current_page = page_no
            buffer = [match.group(2)]
        elif current_no is None:
            if line.strip():
                heading = line.strip().lstrip("# ")
        elif re.match(r"^\s*(?:#{1,4}\s+|第[0-9一二三四五六七八九十百零〇]+[章節篇])", line) and len(line) < 40:
            flush()
            heading = line.strip().lstrip("# ")
            current_no, buffer = None, []
        else:
            buffer.append(line)
    flush()
    return chunks


def _chunk_paragraphs(flat: list[tuple[int | None, str]]) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    heading: str | None = None
    buffer: list[str] = []
    buffer_page: int | None = None
    para_counter = 0

    def flush() -> None:
        nonlocal buffer, para_counter
        if not buffer:
            return
        body = "\n".join(buffer).strip()
        for part in _split_long(body):
            para_counter += 1
            locator = f"第 {buffer_page} 頁 第 {para_counter} 段" if buffer_page else f"第 {para_counter} 段"
            if heading:
                locator = f"{heading[:30]}｜{locator}"
            text = f"{heading}\n{part}" if heading else part
            chunks.append(
                ChunkDraft(seq=len(chunks), locator=locator, article_no=None, page_no=buffer_page,
                           heading=heading, text=text)
            )
        buffer = []

    for page_no, line in flat:
        stripped = line.strip()
        if not stripped:
            if sum(len(b) for b in buffer) >= TARGET_PARA_CHUNK:
                flush()
            continue
        if _STRUCTURAL_HEADING_RE.match(stripped) and len(stripped) < 40:
            flush()
            heading = stripped.lstrip("# ").strip()
            continue
        if _LIST_MARKER_RE.match(stripped) and _is_heading_label(stripped):
            flush()
            heading = stripped.lstrip("# ").strip()
            continue
        if buffer and buffer_page != page_no:
            flush()
        if not buffer:
            buffer_page = page_no
        buffer.append(stripped)
        if sum(len(b) for b in buffer) >= TARGET_PARA_CHUNK:
            flush()
    flush()
    return chunks

