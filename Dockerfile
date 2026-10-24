# NICS Video worker for Linux servers. Models are downloaded at build time so
# the container runs fully offline afterwards (only the jobs API is contacted).
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

ENV NICS_VIDEO_ROOT=/data \
    NICS_VIDEO_MODELS_DIR=/opt/models \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
      --extra-index-url https://download.pytorch.org/whl/cpu

COPY scripts ./scripts
COPY presets ./presets

# Models are baked into the image at /opt/models, outside the /data volume.
RUN python scripts/setup/download_clip.py \
 && python scripts/setup/download_whisper.py \
 && python scripts/setup/download_llm.py

# Optional background music: mount a file at /data/assets/test_music.mp3.
CMD ["python", "scripts/worker.py"]
