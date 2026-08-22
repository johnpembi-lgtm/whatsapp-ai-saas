# Image Python officielle légère
FROM python:3.11-slim

# Répertoire de travail dans le conteneur
WORKDIR /app

# Empêcher Python de générer des fichiers .pyc et forcer l'affichage des logs en temps réel
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Installation des dépendances système nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier l'intégralité du code source
COPY . .

# Exposer le port de l'application
EXPOSE 5000

# Commande d'exécution via Gunicorn (1 worker + 2 threads pour APScheduler)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "wsgi:app"]