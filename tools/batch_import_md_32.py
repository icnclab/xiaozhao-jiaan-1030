from pathlib import Path
from getpass import getpass
import re
import time
import httpx

BASE = "http://127.0.0.1:8140/api"
ROOT = Path(r"C:\Phase1知識庫\小照_正式資料_MD")

VERSION_LABEL = "Phase1_MD_2026-10-06_v1"


def norm(s):
    s = s.strip()
    s = re.sub(r"\.(pdf|txt|docx|md)$", "", s, flags=re.I)
    s = s.replace("－", "-").replace("—", "-")
    s = s.replace("　", " ")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[（）()「」『』《》_\-]", "", s)
    return s.lower()


files = sorted([
    p for p in ROOT.rglob("*.md")
    if "_修正前備份" not in p.name
])

print("=" * 72)
print("小照 Phase 1｜32份 MD 正式版本匯入")
print("=" * 72)
print("MD 數量：", len(files))

if len(files) != 32:
    raise SystemExit(
        f"停止：預期 32 份正式 MD，目前找到 {len(files)} 份。"
    )

username = input("管理員帳號 [admin_happy]: ").strip() or "admin_happy"
password = getpass("管理員密碼: ")

client = httpx.Client(timeout=180)

# 登入
r = client.post(
    f"{BASE}/auth/login",
    json={
        "username": username,
        "password": password,
    },
)
r.raise_for_status()

token = r.json()["session_token"]

client.headers.update({
    "Authorization": f"Bearer {token}"
})

print("\n✓ 登入成功")

# 取得所有文件
r = client.get(f"{BASE}/admin/documents")
r.raise_for_status()

docs = r.json()

doc_by_norm = {}

for d in docs:
    doc_by_norm.setdefault(
        norm(d["title"]),
        []
    ).append(d)

# 先完整配對
pairs = []

for path in files:
    candidates = doc_by_norm.get(
        norm(path.stem),
        []
    )

    if len(candidates) != 1:
        raise SystemExit(
            f"停止：{path.name} 配對數量為 {len(candidates)}，"
            "不進行任何後續匯入。"
        )

    pairs.append(
        (path, candidates[0])
    )

print("✓ 32/32 文件配對完成")

success = []
failed = []
skipped = []

for index, (path, doc) in enumerate(
    pairs,
    start=1
):
    title = doc["title"]
    document_id = doc["id"]

    print("\n" + "=" * 72)
    print(f"[{index}/32] {title}")
    print("DOC =", document_id)

    # 取得目前 published 版本
    published = [
        v
        for v in doc.get("versions", [])
        if v.get("status") == "published"
    ]

    if not published:
        print("✗ 找不到既有 published 版本，跳過")
        failed.append(
            (title, "找不到既有 published 版本")
        )
        continue

    # 取目前最新 published 版本
    current = max(
        published,
        key=lambda v: (
            v.get("effective_from") or "",
            v.get("published_at") or "",
        )
    )

    effective_from = current.get(
        "effective_from"
    )
    source = current.get(
        "source"
    )

    if not effective_from or not source:
        print(
            "✗ 舊版缺少 effective_from 或 source，跳過"
        )
        failed.append(
            (title, "舊版 metadata 不完整")
        )
        continue

    print(
        "  沿用生效日：",
        effective_from
    )
    print(
        "  沿用來源：",
        source
    )

    # 檢查 MD 版本是否已存在
    target = next(
        (
            v
            for v in doc.get("versions", [])
            if v.get("version_label")
            == VERSION_LABEL
        ),
        None,
    )

    if target:
        version_id = target["id"]
        status = target.get("status")

        print(
            "  已存在 MD 版本：",
            version_id
        )
        print(
            "  目前狀態：",
            status
        )

        if status == "published":
            print("  ✓ 已發布，略過")
            skipped.append(title)
            continue

    else:
        # 建立新的 MD 版本
        with path.open("rb") as f:
            r = client.post(
                f"{BASE}/admin/documents/{document_id}/versions",
                data={
                    "version_label":
                        VERSION_LABEL
                },
                files={
                    "file": (
                        path.name,
                        f,
                        "text/plain",
                    )
                },
            )

        if not r.is_success:
            print(
                "  ✗ 上傳失敗：",
                r.status_code,
                r.text
            )
            failed.append(
                (
                    title,
                    f"上傳失敗 {r.status_code}",
                )
            )
            continue

        target = r.json()
        version_id = target["id"]

        print("  ✓ MD 已上傳")
        print(
            "  VER =",
            version_id
        )

    # 等 Worker 解析
    print(
        "  等待 Worker 解析",
        end="",
        flush=True
    )

    parsed = None
    already_published = False

    for _ in range(240):
        time.sleep(1)

        r = client.get(
            f"{BASE}/admin/versions/{version_id}"
        )

        if not r.is_success:
            print()
            print(
                "  ✗ 讀取版本狀態失敗"
            )
            failed.append(
                (
                    title,
                    "讀取版本狀態失敗"
                )
            )
            break

        parsed = r.json()
        status = parsed.get("status")

        if status == "review":
            print()
            print(
                "  ✓ 解析完成：",
                parsed.get(
                    "chunk_count",
                    0
                ),
                "chunks",
            )
            break

        if status == "parse_failed":
            print()
            print(
                "  ✗ 解析失敗：",
                parsed.get(
                    "parse_error"
                )
            )
            failed.append(
                (
                    title,
                    "parse_failed: "
                    + str(
                        parsed.get(
                            "parse_error"
                        )
                    ),
                )
            )
            parsed = None
            break

        if status == "published":
            print()
            print(
                "  ✓ 已經發布"
            )
            success.append(title)
            already_published = True
            parsed = None
            break

        print(
            ".",
            end="",
            flush=True
        )

    else:
        print()
        print(
            "  ✗ Worker 等待逾時"
        )
        failed.append(
            (
                title,
                "Worker timeout"
            )
        )
        parsed = None

    if already_published:
        continue

    if parsed is None:
        continue

    if parsed.get("status") != "review":
        continue

    chunk_count = int(
        parsed.get(
            "chunk_count"
        )
        or 0
    )

    if chunk_count <= 0:
        print(
            "  ✗ chunk_count = 0，不發布"
        )
        failed.append(
            (
                title,
                "chunk_count = 0"
            )
        )
        continue

    # 沿用正式版 metadata
    r = client.patch(
        f"{BASE}/admin/versions/{version_id}",
        json={
            "effective_from":
                effective_from,
            "source":
                source,
        },
    )

    if not r.is_success:
        print(
            "  ✗ metadata 更新失敗：",
            r.status_code,
            r.text
        )
        failed.append(
            (
                title,
                "metadata 更新失敗"
            )
        )
        continue

    print(
        "  ✓ metadata 已沿用"
    )

    # 發布
    r = client.post(
        f"{BASE}/admin/versions/{version_id}/publish"
    )

    if not r.is_success:
        print(
            "  ✗ 發布失敗：",
            r.status_code,
            r.text
        )
        failed.append(
            (
                title,
                f"發布失敗 {r.status_code}",
            )
        )
        continue

    print(
        "  ✓ MD 新版本已發布"
    )

    success.append(title)


print("\n" + "=" * 72)
print("MD 批次更新完成")
print("=" * 72)

print(
    "成功發布：",
    len(success)
)

print(
    "原本已發布／略過：",
    len(skipped)
)

print(
    "失敗：",
    len(failed)
)

if failed:
    print(
        "\n=== 失敗項目 ==="
    )

    for title, reason in failed:
        print(
            "✗",
            title
        )
        print(
            "  ",
            reason
        )

total_done = (
    len(success)
    + len(skipped)
)

print(
    "\n總完成：",
    total_done,
    "/ 32"
)

if (
    total_done == 32
    and not failed
):
    print(
        "\n✓ 32 份正式文件均已有 MD published 版本"
    )
else:
    print(
        "\n⚠ 有項目未完成，先不要進行最終測試。"
    )

client.close()
