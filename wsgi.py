import os
from dotenv import load_dotenv

# Charge les variables d'environnement depuis le fichier .env en mémoire
load_dotenv()

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Démarrage en mode développement sur le port 5000
    app.run(host="0.0.0.0", port=5000, debug=True)