"""Only explicitly reviewed URL-to-version approvals can become official links.
Do not consume generated/LLM-proposed URLs. No server-side HTTP fetching.
"""
from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl

_ALLOWED = {"law.moj.gov.tw", "www.mohw.gov.tw", "mohw.gov.tw", "dep.mohw.gov.tw"}
_APPROVALS = Path(__file__).with_name("jiaan1030_official_approved.json")

def get_reviewed_official_source(version_id: str, stored_url: str | None, title: str) -> dict | None:
    if not stored_url or not title or not _APPROVALS.exists():
        return None
    try:
        data = json.loads(_APPROVALS.read_text(encoding="utf-8"))
        approval = data.get(version_id)
        if not isinstance(approval, dict) or approval.get("reviewed") is not True:
            return None
        if approval.get("url") != stored_url or not approval.get("reviewer"):
            return None
        url = urlsplit(stored_url)
        if url.scheme != "https" or url.hostname not in _ALLOWED:
            return None
        if url.username or url.password or url.port not in (None, 443):
            return None
        if any(k.lower() in {"url", "redirect", "next", "target", "return", "continue"}
               for k, _ in parse_qsl(url.query, keep_blank_values=True)):
            return None
        if any(x in stored_url for x in ("\r", "\n", "\\")):
            return None
        clean = urlunsplit(("https", url.netloc, url.path or "/", url.query, ""))
        return {"title": title, "official_url": clean, "verified": True}
    except (ValueError, TypeError, OSError, UnicodeError):
        return None
