"""初測評測：在獨立的 ltc_eval 資料庫重建合成展示資料，逐題提問並與金標比對。

- 金標（期望出口、期望文件＋版本、禁止引用）寫在 demo/eval/questions.jsonl，執行前已定義。
- 評分全為決定性比對，不用 LLM 自評；引用是否「支持」主張另輸出 CSV 交人工標註。
- 每次結果存 demo/eval/runs/<時間>_<llm>.json，並重新產生 docs/eval-results.md。

用法：
    uv run python scripts/eval_run.py --llm extractive
    uv run python scripts/eval_run.py --llm ollama
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
QUESTIONS = ROOT / "demo" / "eval" / "questions.jsonl"
RUNS = ROOT / "demo" / "eval" / "runs"


def _env_value(key: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].split("#", 1)[0].strip()
    raise RuntimeError(f"找不到 {key}")


def prepare_environment(llm: str) -> str:
    """設定評測用環境變數（必須在 import app 之前）。"""
    base = _env_value("DATABASE_URL")
    eval_url = base.rsplit("/", 1)[0] + "/ltc_eval"
    os.environ.update({
        "DATABASE_URL": eval_url,
        "DATA_DIR": str(Path(_env_value("DATA_DIR")).parent / "eval_data"),
        "LLM_PROVIDER": llm,
        "STT_PROVIDER": "mock",
        "TTS_PROVIDER": "mock",
        "LINE_MODE": "mock",
        "APP_ENV": "dev",
    })
    return eval_url


def ensure_database(eval_url: str) -> None:
    """建立 ltc_eval 資料庫（若不存在）並跑 migration。"""
    from sqlalchemy import create_engine, text

    admin_url = eval_url.rsplit("/", 1)[0] + "/ltc"
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'ltc_eval'")).scalar():
            conn.execute(text("CREATE DATABASE ltc_eval"))
    engine.dispose()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True,
                   env=dict(os.environ, ALEMBIC_DATABASE_URL=eval_url, PYTHONUTF8="1"),
                   capture_output=True)


def score(gold: dict, outcome: str, reason: str | None, cited: list[str], answer: str) -> dict:
    """依金標決定性評分。"""
    expect = gold["expect_outcome"]
    escalated = outcome in {"escalated", "escalation_failed"}
    outcome_ok = (expect == "answered" and outcome == "answered") or (expect == "escalated" and escalated) \
        or expect == "either"
    if gold.get("expect_reason") and escalated:
        outcome_ok = outcome_ok and reason == gold["expect_reason"]
    forbidden = [c for c in cited if any(f in c for f in gold.get("forbid_docs", []))]
    text_violation = [t for t in gold.get("forbid_text", []) if t in (answer or "")]
    citation_hit = None
    if outcome == "answered" and gold.get("expect_docs"):
        citation_hit = any(c in gold["expect_docs"] for c in cited)
    text_ok = None
    if outcome == "answered" and gold.get("expect_text"):
        text_ok = gold["expect_text"] in (answer or "")
    passed = outcome_ok and not forbidden and not text_violation and citation_hit is not False and text_ok is not False
    return {"outcome_ok": outcome_ok, "forbidden_cited": forbidden, "text_violation": text_violation,
            "citation_hit": citation_hit, "text_ok": text_ok, "passed": passed}


def main() -> int:
    """進入點。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", default="extractive", choices=["extractive", "ollama", "mock"])
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()
    eval_url = prepare_environment(args.llm)
    ensure_database(eval_url)
    sys.path.insert(0, str(BACKEND))
    sys.path.insert(0, str(BACKEND / "scripts"))
    from sqlalchemy import select

    import seed_demo
    from app.config import get_settings
    from app.db import new_session
    from app.models import Chunk, Citation, Document, DocumentVersion, User
    from app.providers.llm import warmup
    from app.services import qa_service
    from app.services.qa_policy import DEFAULT_POLICY

    settings = get_settings()
    if not args.no_seed:
        seed_demo.reset()
        seed_demo.seed()
    if args.llm == "ollama":
        warmup()
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    session = new_session()
    results = []
    for gold in questions:
        user = session.scalar(select(User).where(User.username == gold["user"]))
        started = time.perf_counter()
        item, case, _ = qa_service.ask(session, user, question=gold["question"], source="text",
                                       client_request_id=f"eval-{uuid.uuid4()}")
        wall_ms = int((time.perf_counter() - started) * 1000)
        rows = session.execute(
            select(Document.title, DocumentVersion.version_label, Chunk.locator, Chunk.text)
            .select_from(Citation).join(Chunk, Chunk.id == Citation.chunk_id)
            .join(DocumentVersion, DocumentVersion.id == Citation.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Citation.qa_item_id == item.id).order_by(Citation.rank)
        ).all()
        cited = [f"{r.title}|{r.version_label}" for r in rows]
        result = {
            "id": gold["id"], "type": gold["type"], "user": gold["user"], "question": gold["question"],
            "expect_outcome": gold["expect_outcome"], "outcome": item.outcome, "reason": item.escalation_reason,
            "answer": item.answer_text, "cited": cited,
            "citations": [{"doc": f"{r.title}|{r.version_label}", "locator": r.locator, "text": r.text} for r in rows],
            "top_retrieval": (item.checks.get("retrieval") or [{}])[0],
            "llm_error": item.checks.get("llm_error"),
            "llm_http_status": item.checks.get("llm_http_status"),
            "timings_ms": dict(item.timings_ms, wall=wall_ms), "went_to_llm": "generate" in item.timings_ms,
        }
        result.update(score(gold, item.outcome, item.escalation_reason, cited, item.answer_text or ""))
        results.append(result)
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"{mark} {gold['id']} {gold['type']:<13} {item.outcome:<18} {item.escalation_reason or '':<18} "
              f"{wall_ms:>6}ms {cited[:2]}")
    session.close()

    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    meta = {
        "timestamp": stamp, "llm_provider": args.llm, "llm_model": settings.llm_model if args.llm == "ollama" else None,
        "embedding": settings.embedding_provider, "qa_policy": DEFAULT_POLICY.version,
        "policy": {k: getattr(DEFAULT_POLICY, k) for k in
                   ("top_k", "lexical_weight", "min_top_coverage", "min_combined", "min_evidence_score", "min_support")},
        "hardware": {"machine": platform.node(), "cpu": platform.processor(), "os": platform.platform()},
        "concurrency": 1, "n": len(results),
    }
    (RUNS / f"{stamp}_{args.llm}.json").write_text(json.dumps({"meta": meta, "results": results}, ensure_ascii=False,
                                                              indent=1), encoding="utf-8")
    render_report()
    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} 通過；報告：docs/eval-results.md")
    return 0


def _summary(results: list[dict]) -> dict:
    should_escalate = [r for r in results if r["expect_outcome"] == "escalated"]
    should_answer = [r for r in results if r["expect_outcome"] == "answered"]
    answered = [r for r in results if r["outcome"] == "answered" and r.get("citation_hit") is not None]
    llm_times = [r["timings_ms"]["wall"] for r in results if r["went_to_llm"]]
    all_times = [r["timings_ms"]["wall"] for r in results]
    return {
        "passed": (sum(r["passed"] for r in results), len(results)),
        "outcome_ok": (sum(r["outcome_ok"] for r in results), len(results)),
        "refusal_correct": (sum(r["outcome"] != "answered" for r in should_escalate), len(should_escalate)),
        "false_refusal": (sum(r["outcome"] != "answered" for r in should_answer), len(should_answer)),
        "citation_hit": (sum(bool(r["citation_hit"]) for r in answered), len(answered)),
        "forbidden": sum(bool(r["forbidden_cited"]) for r in results),
        "llm_times": llm_times, "all_times": all_times,
    }


def _fmt(pair: tuple[int, int]) -> str:
    num, den = pair
    return f"{num}/{den}（{num / den:.0%}）" if den else "0/0（—）"


def _times(values: list[int]) -> str:
    if not values:
        return "—"
    ordered = sorted(values)
    text = f"n={len(values)}；中位數 {statistics.median(ordered)/1000:.2f}s；最大 {ordered[-1]/1000:.2f}s"
    if len(values) >= 20:
        index = max(0, int(round(0.95 * len(ordered) + 0.5)) - 1)
        text += f"；P95 {ordered[min(index, len(ordered)-1)]/1000:.2f}s"
    else:
        text += "（樣本 < 20，不報 P95）"
    return text


def render_report() -> None:
    """由所有 run JSON 產生 docs/eval-results.md 與人工抽查 CSV（取各 LLM 模式最新一次）。"""
    latest: dict[str, dict] = {}
    for path in sorted(RUNS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        latest[data["meta"]["llm_provider"]] = data
    lines = [
        "# 初測評測結果（合成資料）",
        "",
        "> 自動產生：`backend/scripts/eval_run.py`。題目與金標：`demo/eval/questions.jsonl`（執行前寫定）。",
        "> **全部為合成文件與虛構機構；結果只說明流程與門檻在合成資料上的行為，不代表真實場域表現。**",
        "> 評分是與金標的決定性比對，沒有使用 LLM 自評。引用是否真正「支持」主張，需人工逐筆標註",
        "> `docs/eval-citation-review.csv` 的最後一欄；**人工標註完成前，引用支持度列為未驗證。**",
        "",
    ]
    csv_rows = []
    for provider, data in latest.items():
        meta, results = data["meta"], data["results"]
        s = _summary(results)
        lines += [
            f"## LLM＝{provider}{('（' + meta['llm_model'] + '）') if meta.get('llm_model') else ''}｜{meta['timestamp']}",
            "",
            f"- 政策版本 `{meta['qa_policy']}`；embedding＝{meta['embedding']}；併發＝{meta['concurrency']}；"
            f"機器＝{meta['hardware']['machine']}（{meta['hardware']['cpu']}）",
            f"- 門檻：`{json.dumps(meta['policy'], ensure_ascii=False)}`",
            "",
            "| 指標 | 分子／分母 | 定義 |",
            "|---|---|---|",
            f"| 整題通過 | {_fmt(s['passed'])} | 出口、禁止引用、期望文件、期望文字全部符合 |",
            f"| 出口正確 | {_fmt(s['outcome_ok'])} | 出口（回答／轉人工）與金標一致；「either」題只看禁止條件 |",
            f"| 拒答正確率 | {_fmt(s['refusal_correct'])} | 應轉人工的題目確實轉人工 |",
            f"| 誤拒率 | {_fmt(s['false_refusal'])} | 應可回答的題目卻轉人工（越低越好） |",
            f"| 引用文件＋版本命中 | {_fmt(s['citation_hit'])} | 有回答且有金標文件的題目中，引用含期望文件與版本 |",
            f"| 引用禁止文件 | {s['forbidden']} 題 | 引用了他機構、居家、舊版等不得引用的文件（應為 0） |",
            "",
            f"**延遲（伺服器端 `qa_service.ask` 起訖，含檢索、生成、驗證、寫 DB；不含網路與前端）**",
            f"- 經過生成節點的題目：{_times(s['llm_times'])}",
            f"- 全部題目（含規則直接轉人工）：{_times(s['all_times'])}",
            "",
            "| 題號 | 類型 | 期望 | 實際出口 | 原因 | 引用 | 結果 |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in results:
            cited = "<br>".join(r["cited"]) or "—"
            lines.append(f"| {r['id']} | {r['type']} | {r['expect_outcome']} | {r['outcome']} | {r['reason'] or '—'} "
                         f"| {cited} | {'✅' if r['passed'] else '❌'} |")
            for citation in r["citations"]:
                csv_rows.append([provider, meta["timestamp"], r["id"], r["question"], r["answer"], citation["doc"],
                                 citation["locator"], citation["text"], ""])
        lines.append("")
    (ROOT / "docs" / "eval-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (ROOT / "docs" / "eval-citation-review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["llm", "run", "題號", "問題", "回答", "引用文件", "位置", "引用原文", "人工判定（支持／部分／不支持）"])
        writer.writerows(csv_rows)


if __name__ == "__main__":
    sys.exit(main())
