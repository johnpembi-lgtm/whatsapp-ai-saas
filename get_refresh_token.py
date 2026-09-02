"""
Script à lancer UNE SEULE FOIS en local pour obtenir un refresh_token OAuth2
lié à ton compte Google personnel (pour que la création de Google Sheets
utilise ton quota de 15 Go, pas celui à 0 octet du compte de service).

⚠️ Ne jamais coder CLIENT_ID / CLIENT_SECRET en dur dans ce fichier — ils
sont lus depuis des variables d'environnement pour éviter qu'un secret ne
se retrouve dans l'historique Git si ce fichier est commité par erreur.

Avant de lancer ce script :
1. Crée un fichier .env (à la racine, déjà ignoré par Git) avec :
     GOOGLE_CLIENT_ID=...
     GOOGLE_CLIENT_SECRET=...
   (valeurs obtenues via Google Cloud Console > Identifiants > ID client
   OAuth > type "Application de bureau" — mêmes noms de variables que ceux
   déjà lus par app/services/sheets_service.py)
2. pip install google-auth-oauthlib python-dotenv
3. python get_refresh_token.py
4. Connecte-toi avec ton compte Google dans la fenêtre qui s'ouvre
5. Copie le GOOGLE_REFRESH_TOKEN affiché dans les variables d'environnement
   de Render (jamais dans un fichier commité)
"""
import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit(
        "❌ GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET manquants.\n"
        "Ajoute-les dans un fichier .env local avant de relancer ce script."
    )

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
creds = flow.run_local_server(port=0)

print("\n=== Copie cette valeur dans les variables d'environnement Render ===")
print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")