# PixelIndex API: FastAPI + ONNX CLIP + FAISS + Tesseract.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Python dependencies (cached until requirements.txt changes)
COPY backend/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# 2. CLIP weights baked into the image (cached; ~600 MB for fp32)
ARG ONNX_PRECISION=fp32
ENV VS_MODELS_DIR=/models
COPY docker/fetch_model.py /tmp/fetch_model.py
RUN python /tmp/fetch_model.py ${ONNX_PRECISION} && rm -rf /root/.cache/huggingface /tmp/fetch_model.py

# 3. Application code (unchanged from the repo)
COPY backend/ /app/
COPY docker/backend-entrypoint.sh /usr/local/bin/pixelindex-entrypoint

ENV SEARCH_DATA_DIR=/data \
    VS_ONNX_PRECISION=${ONNX_PRECISION} \
    VS_OCR_ENGINE=auto \
    HF_HUB_OFFLINE=1

VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/system/info', timeout=4)"
ENTRYPOINT ["pixelindex-entrypoint"]
