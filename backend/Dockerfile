# 後端（API 與 worker 共用同一映像；compose 以 command 區分）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"

# ffmpeg：音訊實際解碼驗證、轉檔；容器內 TTS 退為 mock（SAPI 只在 Windows 主機）
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN mkdir -p /data

EXPOSE 8140
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8140"]
