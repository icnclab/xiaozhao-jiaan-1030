"""由 demo/documents/*.src.md 產生 DOCX 與 PDF 合成文件（測試多格式解析）。

需要 dev 相依（python-docx、reportlab）與一個中文 TTF 字型（預設 Windows 標楷體 kaiu.ttf，
可用環境變數 DEMO_PDF_FONT 指定）。產物已提交進版控，一般不需要重跑。

用法：
    uv run python scripts/make_demo_docs.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "demo" / "documents"


def _lines(src: Path) -> list[str]:
    return [line.rstrip() for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]


def make_docx(src: Path, dst: Path) -> None:
    """Markdown 標題（#）轉 Heading 1，其餘為段落。"""
    import docx

    document = docx.Document()
    for line in _lines(src):
        if line.startswith("# "):
            document.add_heading(line[2:], level=1)
        elif line != "@@PAGEBREAK@@":
            document.add_paragraph(line)
    document.save(str(dst))


def make_pdf(src: Path, dst: Path) -> None:
    """用 reportlab 產生可抽取文字的 PDF；`@@PAGEBREAK@@` 換頁（測試頁碼保留）。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font_path = os.environ.get("DEMO_PDF_FONT", r"C:\Windows\Fonts\kaiu.ttf")
    pdfmetrics.registerFont(TTFont("CJK", font_path))
    pdf = canvas.Canvas(str(dst), pagesize=A4)
    width, height = A4
    y = height - 60
    for line in _lines(src):
        if line == "@@PAGEBREAK@@":
            pdf.showPage()
            y = height - 60
            continue
        size = 15 if line.startswith("# ") else 12
        text = line[2:] if line.startswith("# ") else line
        pdf.setFont("CJK", size)
        # 簡單折行：每行最多 38 個全形字
        for start in range(0, len(text), 38):
            pdf.drawString(50, y, text[start : start + 38])
            y -= size + 8
        y -= 4
    pdf.showPage()
    pdf.save()


def main() -> int:
    """產生兩份合成文件。"""
    make_docx(DOCS / "happy_transfer_sop.src.md", DOCS / "happy_transfer_sop.docx")
    make_pdf(DOCS / "happy_incident_sop.src.md", DOCS / "happy_incident_sop.pdf")
    print("已產生 happy_transfer_sop.docx、happy_incident_sop.pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
