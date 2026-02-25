FROM python:3.11-slim

WORKDIR /app

# WeasyPrint 需要的 GTK/Cairo/Pango 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure DB directory exists even before attaching Railway volume.
RUN mkdir -p /data

# SQLite 数据库存储在 Railway 持久化 Volume（/data）
ENV ARCBRIEF_DB_PATH=/data/arcbrief.db

EXPOSE 8000

# workers=1 强制单进程 —— SQLite + APScheduler 不支持多进程并发
# Bind to Railway-provided PORT in production, fallback to 8000 for local docker runs.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips ${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
