# ── 빌드 스테이지 ─────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# 시스템 의존성 (reportlab 폰트/렌더링, chromadb 빌드)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libffi-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        pkg-config \
        libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 설치 (레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ── 런타임 스테이지 ────────────────────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# sentence-transformers 모델 캐시 경로를 컨테이너 내부로 고정
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
ENV HF_HOME=/app/.cache/huggingface

# 런타임 시스템 의존성 (폰트, lxml 등)
# fonts-nanum: NanumGothic 한글 폰트 → /usr/share/fonts/truetype/nanum/
# fonts-noto-cjk: Noto CJK (fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        fonts-nanum \
        fonts-noto-cjk \
        fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

# 빌드 스테이지에서 설치된 패키지 복사
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 앱 소스 복사
COPY app/       ./app/
COPY core/      ./core/
COPY prompts/   ./prompts/
COPY data/laws_registry.json ./data/laws_registry.json
COPY .streamlit/config.toml ./.streamlit/config.toml

# 데이터 디렉토리 생성 (볼륨 마운트 전 owner 설정)
RUN mkdir -p /app/db /app/data/chroma_db /app/.cache/huggingface

# 포트
EXPOSE 8501

# Streamlit 환경 설정
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 실행
CMD ["streamlit", "run", "app/main.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.fileWatcherType=none"]
