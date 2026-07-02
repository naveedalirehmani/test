# Python 3.11 is required: the code uses datetime.UTC (3.11+) and PEP 604
# "X | None" unions.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the whole self-contained app (app code + vendored packages + static).
COPY . .

# Informational only (ignored when using --network host, which we recommend).
EXPOSE 8200

# No --reload in production. Bind 0.0.0.0 so it's reachable on the VPS IP.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8200"]
