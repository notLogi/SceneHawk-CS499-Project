# SceneHawk chatbot service (FastAPI + Chroma RAG).
# Builds a stateless image: the vector index is rebuilt from the committed
# JSONL at startup (see start.sh), so no volume is needed.
FROM python:3.11-slim

# Chroma/onnxruntime need a C runtime; keep the layer small otherwise.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Install deps first so code changes don't bust the pip cache layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + the corpus (data/movies_rag.jsonl is what the index is built from).
COPY src/ ./src/
COPY data/ ./data/
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8000
CMD ["./start.sh"]
