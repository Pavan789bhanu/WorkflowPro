# WorkflowPro backend — FastAPI + Playwright agent
# Playwright's official image ships Chromium + all OS dependencies.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

# Copy application code
COPY app ./app
COPY init_db.py .

# Runtime dirs (screenshots, reports, session state)
RUN mkdir -p /data/captured_dataset /data/browser_session_data /data/appdata

ENV PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    DEFAULT_HEADLESS=true \
    SCREENSHOT_DIR=/data/captured_dataset \
    USER_DATA_DIR=/data/browser_session_data \
    STORAGE_STATE_PATH=/data/appdata/storage_state.json \
    DATA_DIR=/data/appdata \
    DATABASE_URL=sqlite:////data/appdata/ui_capture.db

EXPOSE 8000

# Initialize the DB (idempotent — creates tables + default admin) then serve.
CMD ["sh", "-c", "python init_db.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
