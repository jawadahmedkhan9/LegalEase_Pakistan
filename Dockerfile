# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:18-slim AS frontend-build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY public/ ./public/
COPY src/ ./src/

# Empty string so API calls go to the same origin in production
ENV REACT_APP_API_URL=""
RUN npm run build

# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM python:3.11-slim

# Install system dependencies: Tesseract OCR + shared libs for Pillow/numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python source files
COPY App.py .
COPY education_router.py .
COPY lawyers_router.py .

# Copy JSON data files
COPY *.json ./

# Copy pre-indexed ChromaDB vector data
COPY chroma_db/ ./chroma_db/

# Copy the React build from Stage 1
COPY --from=frontend-build /app/build ./build/

EXPOSE 8000

CMD ["uvicorn", "App:app", "--host", "0.0.0.0", "--port", "8000"]
