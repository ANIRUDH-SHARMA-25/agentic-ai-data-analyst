FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    TMPDIR=/tmp \
    XDG_CACHE_HOME=/tmp/.cache

WORKDIR /app
COPY requirements-frontend.txt ./
RUN python -m pip install --no-cache-dir -r requirements-frontend.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

COPY --chown=10001:10001 frontend/ ./frontend/
COPY --chown=10001:10001 .streamlit/config.toml ./.streamlit/config.toml
COPY --chown=10001:10001 data/sample/retail_sales.csv ./data/sample/retail_sales.csv
USER 10001:10001
EXPOSE 8501
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3).read()"]
CMD ["python", "-m", "streamlit", "run", "frontend/app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true", "--server.fileWatcherType", "none", "--browser.gatherUsageStats", "false"]
