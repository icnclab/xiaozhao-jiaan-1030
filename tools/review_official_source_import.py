"""Read-only preflight for the official-source Excel workbook.

It never writes the approved-source registry or the production database.  The
JSON report is a review artifact; every row still requires a human decision.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from openpyxl import load_workbook

REQUIRED_COLUMNS = (
    "編號", "文件名稱", "文件類型", "原資料來源", "資料顯示日期",
    "官方原文頁面網址", "原始檔名", "人工查核結果", "證據／補充說明", "核准狀態",
)
ALLOWED_HOST_SUFFIXES = (".gov.tw", ".gov.taipei", ".gov.taipei.gov.tw")
APPROVED_WORDS = {"核准", "approved", "yes", "通過"}


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _allowed_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and bool(host) and (
        host.endswith(".gov.tw") or host == "gov.tw" or
        any(host.endswith(suffix) for suffix in ALLOWED_HOST_SUFFIXES)
    )


def review(path: Path) -> dict:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    header = tuple(_text(v) for v in next(rows, ()))
    missing = [name for name in REQUIRED_COLUMNS if name not in header]
    if missing:
        return {"status": "invalid", "missing_columns": missing, "rows": [], "safe_to_import": False}
    positions = {name: header.index(name) for name in REQUIRED_COLUMNS}
    parsed = []
    for row_number, values in enumerate(rows, start=2):
        row = {name: _text(values[idx] if idx < len(values) else None) for name, idx in positions.items()}
        if not any(row.values()):
            continue
        issues = []
        for name in ("編號", "文件名稱", "文件類型", "官方原文頁面網址", "原始檔名"):
            if not row[name]:
                issues.append(f"缺少{name}")
        if row["官方原文頁面網址"] and not _allowed_url(row["官方原文頁面網址"]):
            issues.append("網址不是允許的 HTTPS 政府網域")
        requested_approval = row["核准狀態"].casefold() in APPROVED_WORDS
        if requested_approval and not row["人工查核結果"]:
            issues.append("要求核准但缺少人工查核結果")
        parsed.append({"row": row_number, "data": row, "issues": issues,
                       "requested_approval": requested_approval, "decision": "PENDING_HUMAN_REVIEW"})

    names = Counter(item["data"]["文件名稱"].casefold() for item in parsed if item["data"]["文件名稱"])
    urls = Counter(item["data"]["官方原文頁面網址"].casefold() for item in parsed if item["data"]["官方原文頁面網址"])
    for item in parsed:
        row = item["data"]
        if row["文件名稱"] and names[row["文件名稱"].casefold()] > 1:
            item["issues"].append("文件名稱重複，須人工核對版本／日期／附件")
        if row["官方原文頁面網址"] and urls[row["官方原文頁面網址"].casefold()] > 1:
            item["issues"].append("官方網址重複，須確認是否為同一文件或附件頁")

    return {
        "status": "review_required", "source": str(path), "row_count": len(parsed),
        "issue_count": sum(bool(item["issues"]) for item in parsed),
        "requested_approval_count": sum(item["requested_approval"] for item in parsed),
        "approved_count": 0,
        "safe_to_import": False,
        "note": "本工具只產生預覽；不會自動核准、模糊匹配或寫入正式資料。",
        "rows": parsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = review(args.workbook.resolve())
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "review_required" else 2


if __name__ == "__main__":
    raise SystemExit(main())
