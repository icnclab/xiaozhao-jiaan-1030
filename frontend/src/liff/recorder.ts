/**
 * 錄音與免手（喚醒詞）工具。
 *
 * - `checkCapability()`：先檢查 getUserMedia／MediaRecorder 與可用格式，不支援時由頁面提供替代入口。
 * - `Recorder`：MediaRecorder 包裝；停止後把 Blob 交給上傳流程，不存 localStorage。
 * - `WakeListener`：以瀏覽器 Web Speech API 偵測喚醒詞（例：「小照你好」）。
 *   ⚠ Web Speech API 會把麥克風音訊送到瀏覽器廠商的語音服務（Google／Apple）；只用於偵測喚醒詞，
 *   使用者開啟「免手模式」前會看到此說明。iOS／Android 的 LINE 內建瀏覽器支援度未實測。
 * - `SilenceDetector`：AnalyserNode 音量偵測，免手模式下靜音自動停止。
 */

export interface Capability {
  ok: boolean;
  mime: string | null;
  reason: string | null;
  speechRecognition: boolean;
}

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/aac",
  "audio/wav",
];

export function checkCapability(): Capability {
  const speechRecognition = Boolean(
    (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition,
  );
  if (!window.isSecureContext) {
    return { ok: false, mime: null, reason: "此頁面不是 HTTPS，瀏覽器不允許使用麥克風", speechRecognition };
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return { ok: false, mime: null, reason: "此瀏覽器不支援麥克風擷取（getUserMedia）", speechRecognition };
  }
  if (typeof MediaRecorder === "undefined") {
    return { ok: false, mime: null, reason: "此瀏覽器不支援 MediaRecorder", speechRecognition };
  }
  const mime = MIME_CANDIDATES.find((m) => {
    try {
      return MediaRecorder.isTypeSupported(m);
    } catch {
      return false;
    }
  });
  if (!mime) return { ok: false, mime: null, reason: "此瀏覽器沒有可用的錄音格式", speechRecognition };
  return { ok: true, mime, reason: null, speechRecognition };
}

export class Recorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private startedAt = 0;
  private timer: number | null = null;
  readonly mime: string;

  constructor(mime: string) {
    this.mime = mime;
  }

  get elapsedMs(): number {
    return this.startedAt ? Date.now() - this.startedAt : 0;
  }

  /** 取得麥克風並開始錄音；`maxSec` 到達時自動停止並呼叫 onAutoStop。 */
  async start(maxSec: number, onAutoStop: () => void, existingStream?: MediaStream): Promise<MediaStream> {
    this.stream = existingStream ?? (await navigator.mediaDevices.getUserMedia({ audio: true }));
    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream, { mimeType: this.mime });
    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.recorder.start(1000);
    this.startedAt = Date.now();
    this.timer = window.setTimeout(onAutoStop, maxSec * 1000);
    return this.stream;
  }

  /** 停止並回傳音訊 Blob。 */
  stop(): Promise<Blob> {
    return new Promise((resolve) => {
      if (this.timer) window.clearTimeout(this.timer);
      const recorder = this.recorder;
      if (!recorder || recorder.state === "inactive") {
        this.release();
        resolve(new Blob(this.chunks, { type: this.mime }));
        return;
      }
      recorder.onstop = () => {
        this.release();
        resolve(new Blob(this.chunks, { type: this.mime }));
      };
      recorder.stop();
    });
  }

  cancel(): void {
    if (this.timer) window.clearTimeout(this.timer);
    try {
      if (this.recorder && this.recorder.state !== "inactive") this.recorder.stop();
    } catch {
      /* ignore */
    }
    this.chunks = [];
    this.release();
  }

  private release(): void {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.recorder = null;
    this.startedAt = 0;
  }
}

/** 音量偵測：說過話之後連續靜音 `silenceMs` 就觸發。 */
export class SilenceDetector {
  private ctx: AudioContext | null = null;
  private raf = 0;

  start(stream: MediaStream, onSilence: () => void, silenceMs = 1800, threshold = 0.012): void {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.ctx = new Ctx();
    const source = this.ctx.createMediaStreamSource(stream);
    const analyser = this.ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const buffer = new Float32Array(analyser.fftSize);
    let spoke = false;
    let quietSince = 0;
    const tick = () => {
      analyser.getFloatTimeDomainData(buffer);
      let sum = 0;
      for (const v of buffer) sum += v * v;
      const rms = Math.sqrt(sum / buffer.length);
      const now = performance.now();
      if (rms > threshold) {
        spoke = true;
        quietSince = 0;
      } else if (spoke) {
        if (!quietSince) quietSince = now;
        else if (now - quietSince > silenceMs) {
          onSilence();
          return;
        }
      }
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  stop(): void {
    cancelAnimationFrame(this.raf);
    this.ctx?.close().catch(() => undefined);
    this.ctx = null;
  }
}

function normalizeForMatch(text: string): string {
  return text.replace(/[\s,，、。:：!！?？~～]/g, "").toLowerCase();
}

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

/** 喚醒詞聆聽器（Web Speech API）。 */
export class WakeListener {
  private recognition: SpeechRecognitionLike | null = null;
  private stopped = true;

  constructor(private wakeWords: string[]) {}

  static supported(): boolean {
    return checkCapability().speechRecognition;
  }

  start(onWake: (heard: string) => void, onError: (message: string) => void): void {
    const Ctor = (window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecognitionLike }).webkitSpeechRecognition;
    if (!Ctor) {
      onError("此瀏覽器不支援語音辨識，無法使用喚醒詞");
      return;
    }
    const words = this.wakeWords.map(normalizeForMatch).filter(Boolean);
    this.stopped = false;
    const recognition = new Ctor();
    recognition.lang = "zh-TW";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (e) => {
      const last = e.results[e.results.length - 1];
      const heard = normalizeForMatch(last[0].transcript);
      if (words.some((w) => heard.includes(w))) {
        this.stop();
        onWake(last[0].transcript);
      }
    };
    recognition.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        this.stopped = true;
        onError("麥克風或語音辨識權限被拒絕");
      }
    };
    recognition.onend = () => {
      if (!this.stopped) {
        try {
          recognition.start(); // 瀏覽器會自動結束連續辨識，未停止前就重啟
        } catch {
          /* ignore */
        }
      }
    };
    this.recognition = recognition;
    try {
      recognition.start();
    } catch (err) {
      onError(err instanceof Error ? err.message : "語音辨識啟動失敗");
    }
  }

  stop(): void {
    this.stopped = true;
    try {
      this.recognition?.abort();
    } catch {
      /* ignore */
    }
    this.recognition = null;
  }
}

/** 短提示音（喚醒成功）。 */
export function beep(): void {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.value = 0.08;
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.18);
    osc.onended = () => ctx.close();
  } catch {
    /* ignore */
  }
}
