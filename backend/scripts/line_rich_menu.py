"""建立並套用 LINE 圖文選單（rich menu）：問 AI／錄音／問題分類／我的案件／使用說明／小照你好。

- 有 LIFF_ID 時六格用 uri 動作直接開 LIFF 頁；否則用 message 動作送出關鍵字（bot 會回 LIFF 連結）。
- 圖片以 Pillow 產生（2500×843，六格），字型預設 Windows 標楷體，可用 --font 指定。
- token 只從 .env 讀。用法：
    uv run python scripts/line_rich_menu.py            # 建立＋上傳圖片＋設為預設
    uv run python scripts/line_rich_menu.py --delete-others   # 另外刪掉舊的選單
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402

API = "https://api.line.me"
DATA_API = "https://api-data.line.me"
W, H = 2500, 843
CELLS = [
    ("問 AI", "💬", "ask"),
    ("錄音／談話", "🎙", "record"),
    ("問題分類", "📋", "report"),
    ("我的案件", "📂", "cases"),
    ("使用說明", "📖", "help"),
    ("小照你好", "👋", None),
]
MENU_TEXT = {"ask": "問 AI", "record": "錄音", "report": "問題分類", "cases": "我的案件", "help": "使用說明"}


def build_image(font_path: str) -> bytes:
    """畫六格選單圖。"""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (W, H), "#f6f7f9")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 88)
    small = ImageFont.truetype(font_path, 44)
    cell_w, cell_h = W // 3, H // 2
    for index, (label, _, _) in enumerate(CELLS):
        x0, y0 = (index % 3) * cell_w, (index // 3) * cell_h
        draw.rectangle([x0 + 18, y0 + 18, x0 + cell_w - 18, y0 + cell_h - 18], fill="white", outline="#cfe8e5", width=6)
        draw.rounded_rectangle([x0 + 18, y0 + 18, x0 + cell_w - 18, y0 + 46], radius=6, fill="#0f766e")
        tw = draw.textlength(label, font=font)
        draw.text((x0 + (cell_w - tw) / 2, y0 + cell_h / 2 - 70), label, fill="#1f2933", font=font)
        hint = "只回答有出處的規範問題" if index == 0 else ""
        if hint:
            hw = draw.textlength(hint, font=small)
            draw.text((x0 + (cell_w - hw) / 2, y0 + cell_h / 2 + 40), hint, fill="#6b7280", font=small)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def build_menu(liff_id: str) -> dict:
    """組 rich menu 物件。"""
    cell_w, cell_h = W // 3, H // 2
    areas = []
    for index, (label, _, page) in enumerate(CELLS):
        bounds = {"x": (index % 3) * cell_w, "y": (index // 3) * cell_h, "width": cell_w, "height": cell_h}
        if page is None:
            action = {"type": "message", "label": label, "text": "小照你好"}
        elif liff_id:
            action = {"type": "uri", "label": label, "uri": f"https://liff.line.me/{liff_id}/{page}"}
        else:
            action = {"type": "message", "label": label, "text": MENU_TEXT[page]}
        areas.append({"bounds": bounds, "action": action})
    return {"size": {"width": W, "height": H}, "selected": True, "name": "小照主選單",
            "chatBarText": "開啟選單", "areas": areas}


def main() -> int:
    """進入點。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", default=r"C:\Windows\Fonts\kaiu.ttf")
    parser.add_argument("--delete-others", action="store_true")
    args = parser.parse_args()
    s = get_settings()
    if not s.line_channel_access_token:
        print("LINE_CHANNEL_ACCESS_TOKEN 未設定")
        return 1
    headers = {"Authorization": f"Bearer {s.line_channel_access_token}"}
    with httpx.Client(timeout=30, headers=headers) as client:
        r = client.post(f"{API}/v2/bot/richmenu", json=build_menu(s.liff_id))
        if r.status_code != 200:
            print("建立失敗：", r.status_code, r.text[:300])
            return 1
        menu_id = r.json()["richMenuId"]
        print("rich menu 已建立：", menu_id)
        r = client.post(f"{DATA_API}/v2/bot/richmenu/{menu_id}/content", content=build_image(args.font),
                        headers={"Content-Type": "image/png"})
        if r.status_code != 200:
            print("上傳圖片失敗：", r.status_code, r.text[:300])
            return 1
        r = client.post(f"{API}/v2/bot/user/all/richmenu/{menu_id}")
        print("設為預設選單：", "OK" if r.status_code == 200 else f"HTTP {r.status_code} {r.text[:200]}")
        if args.delete_others:
            for item in client.get(f"{API}/v2/bot/richmenu/list").json().get("richmenus", []):
                if item["richMenuId"] != menu_id:
                    client.delete(f"{API}/v2/bot/richmenu/{item['richMenuId']}")
                    print("已刪除舊選單：", item["richMenuId"])
    print("提示：LIFF_ID 未設定時六格改送關鍵字，bot 回 LIFF 連結；設定後重跑本腳本改為直接開頁。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
