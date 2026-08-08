# Image Python officielle légère
FROM python:3.11-slim

# Répertoire de travail dans le conteneur
WORKDIR /app

# Empêcher Python de générer des fichiers .pyc et forcer l'affichage des logs en temps réel
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copier et installer les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier l'intégralité du code source
COPY . .

# Exposer le port de l'application
EXPOSE 5000

# Commande d'exécution via Gunicorn
# --threads=2 permet au planificateur (APScheduler) de tourner sereinement en arrière-plan
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "wsgi:app"]