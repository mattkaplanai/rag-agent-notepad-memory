FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir django djangorestframework django-cors-headers openpyxl rank_bm25

# Copy application code
COPY app/ ./app/
COPY api/ ./api/
COPY data/ ./data/

EXPOSE 7861 8000
