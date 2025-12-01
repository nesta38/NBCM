FROM python:3.11-slim

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code application
COPY . .

# Créer les répertoires nécessaires
RUN mkdir -p /app/data/db /app/data/altaview_auto_import /app/logs

# Variables d'environnement
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Port
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:5000/api/v1/health || exit 1

# Entrypoint
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "300", "run:app"]

