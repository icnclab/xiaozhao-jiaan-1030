from pathlib import Path
import sys

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.review_official_source_import import REQUIRED_COLUMNS, review  # noqa: E402


def test_official_source_preflight_never_approves(tmp_path: Path):
    path = tmp_path / "sources.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(REQUIRED_COLUMNS)
    sheet.append((1, "測試辦法", "法規", "主管機關", "2026-01-01",
                  "https://law.moj.gov.tw/Test", "test.pdf", "已人工核對", "頁面與附件一致", "核准"))
    workbook.save(path)
    result = review(path)
    assert result["status"] == "review_required"
    assert result["requested_approval_count"] == 1
    assert result["approved_count"] == 0
    assert result["safe_to_import"] is False
    assert result["rows"][0]["decision"] == "PENDING_HUMAN_REVIEW"


def test_official_source_preflight_rejects_non_allowlisted_and_duplicates(tmp_path: Path):
    path = tmp_path / "sources.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(REQUIRED_COLUMNS)
    for number in (1, 2):
        sheet.append((number, "同名手冊", "手冊", "未知", "2026-01-01",
                      "https://example.com/manual", f"manual-{number}.pdf", "", "", ""))
    workbook.save(path)
    result = review(path)
    assert result["issue_count"] == 2
    assert all("網址不是允許的 HTTPS 政府網域" in row["issues"] for row in result["rows"])
    assert all(any("文件名稱重複" in issue for issue in row["issues"]) for row in result["rows"])
