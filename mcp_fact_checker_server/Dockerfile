FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m spacy download en_core_web_sm

# Pre-download HF models to cache
RUN python -c "from transformers import AutoModel, AutoTokenizer; \
    print('Downloading DistilBERT...'); \
    AutoModel.from_pretrained('distilbert-base-uncased-finetuned-sst-2-english'); \
    AutoTokenizer.from_pretrained('distilbert-base-uncased-finetuned-sst-2-english'); \
    print('Downloading RoBERTa...'); \
    AutoModel.from_pretrained('roberta-base'); \
    AutoTokenizer.from_pretrained('roberta-base'); \
    print('Downloading Sentence Transformer...'); \
    from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('BAAI/bge-large-en-v1.5'); \
    print('Models downloaded successfully.')"

COPY ./app /app/app

ENV PYTHONPATH=/app

RUN useradd -m appuser && chown -R appuser /app
RUN mkdir -p /logs && chown -R appuser /logs
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]