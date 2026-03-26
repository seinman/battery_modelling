FROM python:3.12-slim

WORKDIR /app

# System build deps (needed for some scientific Python wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies before copying application code
# so this layer is cached as long as pyproject.toml doesn't change.
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application source
COPY electronic_union/ ./electronic_union/
COPY app/ ./app/

# Copy pre-computed scenario data.
# Run `python scripts/precompute.py` locally before `docker build`.
COPY data/ ./data/

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app/main.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
