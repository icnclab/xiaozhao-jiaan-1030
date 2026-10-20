"""Download fixed official evidence sources into research folder only. No app/DB imports."""
import concurrent.futures
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "quality_tests/recall_round1/evidence_review/official_review_20261016"
SOURCES = {
    "law_current.html": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070059",
    "law_history.html": "https://law.moj.gov.tw/LawClass/LawHistory.aspx?pcode=L0070059",
    "law_20220120.html": "https://law.moj.gov.tw/LawClass/LawOldVer.aspx?lnndate=20220120&lser=001&pcode=L0070059",
    "annex4_current.pdf": "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000398331&lan=C",
    "manual_landing.html": "https://1966.gov.tw/LTC/cp-7565-86698-207.html",
    "manual_official.pdf": "https://www.mohw.gov.tw/dl-100619-d08f6862-e9f4-48be-99cb-a79d0bb0b2f9.html",
    "amendment_landing.html": "https://www.mohw.gov.tw/cp-7186-82814-1.html",
    "amendment_order_20250619.pdf": "https://www.mohw.gov.tw/dl-96429-c3652d8d-7f6f-484d-b91b-880fded89c83.html",
    "amendment_comparison_20250619.pdf": "https://www.mohw.gov.tw/dl-96430-927a14bd-adf8-4254-9aba-272e61b26e84.html",
    "amendment_combined_20250619.pdf": "https://www.mohw.gov.tw/dl-96432-db9a3724-e14c-4ec5-9b00-09babfdf07ff.html",
    "correction_20251003.pdf": "https://gazette.nat.gov.tw/EG_FileManager/eguploadpub/eg031189/ch08/type7/gov70/num40/Eg.pdf",
    "ba16_notice_landing.html": "https://www.health.taichung.gov.tw/26198/1614263/1617520/1617525/1617526/3231141",
    "ba16_notice_20260305.pdf": "https://www.health.taichung.gov.tw" + quote("/media/1385516/1150305-重申提供長照服務應落實確認個案服務使用情形-異常事件通報等.pdf", safe="/"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supplement", action="store_true")
    args = parser.parse_args()
    target = OUT / "sources"; target.mkdir(parents=True, exist_ok=True)
    manifest = OUT / ("official_sources_supplement.json" if args.supplement else "official_sources.json")
    if manifest.exists():
        raise SystemExit("Refusing to overwrite source capture")
    selected = dict(SOURCES)
    if args.supplement:
        previous = json.loads((OUT / "official_sources.json").read_text(encoding="utf-8"))
        selected = {k: v for k, v in selected.items() if k not in previous}
    def fetch(pair):
        name, url = pair
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=35) as response:
                final = response.geturl()
                if urlsplit(final).scheme != "https" or urlsplit(final).hostname not in {
                    "law.moj.gov.tw", "www.mohw.gov.tw", "1966.gov.tw", "gazette.nat.gov.tw", "www.health.taichung.gov.tw"}:
                    raise ValueError("Unexpected redirect")
                content = response.read(30 * 1024 * 1024 + 1)
                if len(content) > 30 * 1024 * 1024:
                    raise ValueError("Oversized source")
                if name.endswith(".pdf") and not content.startswith(b"%PDF"):
                    raise ValueError("Not a PDF")
                path = target / name
                if path.exists():
                    raise ValueError("Source already exists")
                path.write_bytes(content)
                return name, {"url": url, "final_url": final, "status": "downloaded",
                              "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
                              "captured_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat()}
        except Exception as exc:
            return name, {"url": url, "status": "unavailable", "reason": type(exc).__name__ + ": " + str(exc)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = dict(pool.map(fetch, selected.items()))
    manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v["status"] for k, v in rows.items()}))


if __name__ == "__main__":
    main()
