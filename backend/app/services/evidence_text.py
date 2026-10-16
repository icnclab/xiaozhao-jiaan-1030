"""Shared substantive-body view; source text and displayed locators stay intact."""
import re
from app.services.text import normalize

_BOILERPLATE = re.compile(r'^(?:<!--|地址[：:]|聯絡|傳真|電子郵件|受文者|發文日期|發文字號|速別|密等|附件[：:]|正本[：:]|副本[：:]|主旨[：:]|第\d+頁)')


def substantive_body(text: str) -> str:
    """Ignore headings/letter metadata, preserve boundaries, join PDF wraps."""
    lines = []
    skipping_subject = False
    for raw in text.splitlines():
        line = normalize(raw).strip()
        if not line:
            continue
        if line.startswith(('主旨：', '主旨:')):
            skipping_subject = True
        if line.startswith(('說明：', '說明:', '一、', '二、', '三、', '四、')):
            skipping_subject = False
        if skipping_subject or _BOILERPLATE.search(line) or line.startswith('#'):
            continue
        lines.append(line)
    return ''.join(lines)
