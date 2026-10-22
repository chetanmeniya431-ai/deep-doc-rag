FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/data/models \
    FASTEMBED_CACHE_PATH=/app/data/models

# Tesseract reads text inside chart images. Fonts give the PDF generator real glyphs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
CMD ["uvicorn", "deepdoc.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
