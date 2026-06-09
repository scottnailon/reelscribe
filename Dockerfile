FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY reelscribe.py .

# whisper models cache here; mount a volume to persist between runs
ENV HF_HUB_CACHE=/models
VOLUME ["/models", "/out"]

ENTRYPOINT ["python", "reelscribe.py"]
CMD ["--help"]
