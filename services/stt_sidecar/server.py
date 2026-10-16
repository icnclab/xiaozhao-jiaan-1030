"""faster-whisper STT sidecar：模型常駐、以 HTTP 接收 16 kHz wav、回傳分段。

只用標準庫 http.server（asr venv 不需額外相依）。啟動：
    C:\\Users\\tsai_\\venvs\\asr\\Scripts\\python.exe services/stt_sidecar/server.py --port 8147 --model large-v3

端點：
    GET  /healthz                      → {"ok": true, "model": "...", "device": "cuda|cpu"}
    POST /transcribe?model=large-v3    body=audio/wav → {"segments": [...], "language": "zh", "model": "..."}

輸出片段 `uncertain` 的判定：faster-whisper 的 avg_logprob < -0.8 或 no_speech_prob > 0.5。
說話者分段不在此處（見 backend/app/providers/diarization.py：MVP 一律「未辨識」，由人確認）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def _register_nvidia_dlls() -> None:
    """把 pip 安裝的 CUDA DLL 目錄加進 Windows DLL 搜尋路徑（ctranslate2 需要）。"""
    if os.name != "nt":
        return
    for root in sys.path:
        nvidia_root = os.path.join(root, "nvidia")
        if not os.path.isdir(nvidia_root):
            continue
        for entry in os.listdir(nvidia_root):
            bin_dir = os.path.join(nvidia_root, entry, "bin")
            if os.path.isdir(bin_dir):
                try:
                    os.add_dll_directory(bin_dir)
                except OSError:
                    pass
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


_register_nvidia_dlls()

from faster_whisper import WhisperModel  # noqa: E402

try:
    from opencc import OpenCC

    _to_tw = OpenCC("s2twp").convert
except Exception:  # opencc 未安裝時原樣輸出
    def _to_tw(text: str) -> str:
        return text


class Engine:
    """模型快取＋單一推論鎖（10 GB 顯存不適合同時多路推論）。"""

    def __init__(self, device: str) -> None:
        self.device = device
        self.models: dict[str, WhisperModel] = {}
        self.lock = threading.Lock()

    def get(self, name: str) -> WhisperModel:
        """取得（或載入）模型。"""
        if name not in self.models:
            compute = "float16" if self.device == "cuda" else "int8"
            try:
                self.models[name] = WhisperModel(name, device=self.device, compute_type=compute)
            except Exception as exc:
                if self.device == "cuda":
                    sys.stderr.write(f"[warn] CUDA load failed ({type(exc).__name__}); falling back to CPU int8\n")
                    self.device = "cpu"
                    self.models[name] = WhisperModel(name, device="cpu", compute_type="int8")
                else:
                    raise
        return self.models[name]

    def transcribe(self, wav_path: str, name: str) -> dict:
        """轉錄一個 16 kHz wav。

        Args:
            wav_path: 音檔路徑。
            name: 模型名稱。

        Returns:
            含 segments、language、model、elapsed_ms 的字典。
        """
        with self.lock:
            model = self.get(name)
            started = time.perf_counter()
            raw, info = model.transcribe(
                wav_path, language="zh", vad_filter=True, beam_size=2, condition_on_previous_text=False,
                # initial_prompt 讓模型偏向正體中文與本系統用語（含喚醒詞「小照」的寫法）
                initial_prompt="以下是照顧服務員在長照機構的對話，使用臺灣的正體中文。小照你好，家屬要我代購成藥可以嗎？",
                vad_parameters={"min_silence_duration_ms": 400},
            )
            segments = []
            for seg in raw:
                text = _to_tw(seg.text.strip())
                if not text:
                    continue
                segments.append({
                    "start_ms": int(seg.start * 1000),
                    "end_ms": int(seg.end * 1000),
                    "text": text,
                    "uncertain": bool(seg.avg_logprob < -0.8 or seg.no_speech_prob > 0.5),
                })
            return {"segments": segments, "language": info.language, "model": f"faster-whisper/{name}",
                    "device": self.device, "elapsed_ms": int((time.perf_counter() - started) * 1000)}


ENGINE: Engine
DEFAULT_MODEL = "large-v3"


class Handler(BaseHTTPRequestHandler):
    """HTTP 處理器。"""

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401
        """只記路徑與狀態，不記內容。"""
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path == "/healthz":
            self._json(200, {"ok": True, "model": DEFAULT_MODEL, "device": ENGINE.device,
                             "loaded": sorted(ENGINE.models)})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/transcribe":
            self._json(404, {"error": "not found"})
            return
        model = parse_qs(parsed.query).get("model", [DEFAULT_MODEL])[0]
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 200 * 1024 * 1024:
            self._json(413, {"error": "bad length"})
            return
        data = self.rfile.read(length)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            handle.write(data)
            path = handle.name
        try:
            self._json(200, ENGINE.transcribe(path, model))
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": type(exc).__name__})
        finally:
            os.unlink(path)


def main() -> None:
    """進入點。"""
    global ENGINE, DEFAULT_MODEL
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8147)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    args = parser.parse_args()
    DEFAULT_MODEL = args.model
    ENGINE = Engine(args.device)
    sys.stderr.write(f"loading {args.model} on {args.device}...\n")
    ENGINE.get(args.model)
    sys.stderr.write(f"stt sidecar ready on http://{args.host}:{args.port} (device={ENGINE.device})\n")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
