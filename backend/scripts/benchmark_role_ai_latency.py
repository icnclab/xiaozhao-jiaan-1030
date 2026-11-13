"""Non-persistent Ollama latency probe with synthetic evidence only."""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.providers.llm import EvidenceItem, OllamaLlm
from app.config import get_settings

QUESTIONS = [
    "服務異常時督導應先確認什麼？", "照服員回報跌倒後要留下哪些紀錄？",
    "主任發現案件長期未結案應如何管理？", "文件依據不足時可以直接核准嗎？",
    "個案家屬要求變更服務內容時要怎麼處理？", "重大事件應在何時升級？",
    "如何確認照服員已依流程完成回報？", "主管可以依口頭說明省略紀錄嗎？",
    "知識庫來源尚未核准時應如何顯示？", "跨機構案件可以直接查看嗎？",
]
EVIDENCE = [EvidenceItem(
    ref="E1", chunk_id="synthetic", title="合成測試規範", locator="測試條文",
    version_label="測試版", effective_from="2026-01-01",
    text="遇到異常事件應先確認人員安全、依機構流程回報並留下紀錄；資料與案件僅限授權組織及角色存取。來源未經人工核准時應標示待確認，不得自動核准。",
)]


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * p + 0.999999)))]


def main() -> int:
    settings = get_settings()
    provider = OllamaLlm(settings.ollama_base_url, settings.llm_model, settings.llm_timeout_sec)
    rows = []
    for index, question in enumerate(QUESTIONS):
        started = time.perf_counter()
        answer = provider.answer(question, EVIDENCE, role=("supervisor", "director", "admin")[index % 3])
        elapsed = (time.perf_counter() - started) * 1000
        rows.append({"case": index + 1, "elapsed_ms": round(elapsed, 1), "raw_ok": answer.raw_ok,
                     "needs_human": answer.needs_human, "ollama": answer.metrics})
        print(f"case {index + 1}/10 {elapsed:.1f} ms", flush=True)
    values = [row["elapsed_ms"] for row in rows]
    report = {
        "scope": "Ollama model layer only; synthetic evidence; no API/DB writes",
        "model": settings.llm_model,
        "cold_first_ms": values[0],
        "warm_p50_ms": round(statistics.median(values[1:]), 1),
        "warm_p95_ms": round(percentile(values[1:], .95), 1),
        "slowest_ms": max(values),
        "rows": rows,
    }
    output = Path(__file__).resolve().parents[2] / "docs" / "third_round_ollama_latency.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
