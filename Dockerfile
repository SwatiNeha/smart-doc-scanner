# Dockerfile (single container for FastAPI + Streamlit)
FROM python:3.11-slim

# System deps: Tesseract for OCR + libraries needed by OpenCV wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements early to leverage Docker layer cache
# Make sure these files are NOT excluded by .dockerignore
COPY requirements.txt ./

# Prefer wheels to avoid building from source inside the container
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

# Install Python deps (backend + frontend)
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy app code
COPY fastapi_appnew.py app_streamlit.py start.sh ./
RUN chmod +x start.sh

# Runtime env (safe defaults; set real values at docker run time)
ENV OLLAMA_BASE=http://host.docker.internal:11434/v1 \
    LLM_MODEL=gemma3:latest \
    API_BASE=http://127.0.0.1:8001 \
    STREAMLIT_SERVER_PORT=8501 \
    PYTHONUNBUFFERED=1

EXPOSE 8001 8501
ENV API_BASE=http://127.0.0.1:8001

CMD ["./start.sh"]
