import csv
import io
import json
import os
import gspread
import requests


class SheetsService:
    """Service pour interagir avec le catalogue et les commandes Google Sheets des boutiques."""

    HEADERS = ["nom", "description", "prix", "stock", "image_url"]

    @staticmethod
    def get_gspread_client():
        """
        Initialise le client gspread.
        Essaie d'abord via le fichier physique local credentials.json,
        sinon lit le JSON depuis la variable d'environnement GOOGLE_CREDENTIALS_JSON.
        """
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        creds_path = os.path.join(base_dir, "credentials.json")

        # 1. Vérification si le fichier local existe (Environnement de Dev)
        if os.path.exists(creds_path):
            try:
                return gspread.service_account(filename=creds_path)
            except Exception as e:
                print(f"❌ Erreur lors du chargement de {creds_path} : {e}")

        # 2. Sinon, lecture depuis la variable d'environnement (Environnement Render/Production)
        creds_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_env:
            try:
                creds_dict = json.loads(creds_env)
                return gspread.service_account_from_dict(creds_dict)
            except Exception as e:
                print(f"❌ Erreur lors du parsing de GOOGLE_CREDENTIALS_JSON : {e}")
                return None

        print("❌ Aucune méthode d'authentification Google valide trouvée (ni fichier local, ni variable GOOGLE_CREDENTIALS_JSON).")
        return None