FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir django djangorestframework django-cors-headers openpyxl rank_bm25 pytest pytest-django

# Copy application code
COPY app/ ./app/
COPY api/ ./api/
COPY data/ ./data/
COPY tests/ ./tests/

# Run Django migrations at build time
RUN cd api && python manage.py migrate --noinput

EXPOSE 7861 8000
