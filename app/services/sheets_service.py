import csv
import io
import json
import os
import gspread
import requests
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google.auth.transport.requests import Request


class SheetsService:
    """Service pour interagir avec le catalogue et les commandes Google Sheets des boutiques."""

    HEADERS = ["nom", "description", "prix", "stock", "image_url"]

    @staticmethod
    def _get_google_credentials():
        """
        Récupère et valide les identifiants Google.
        Priorité 1 : OAuth2 Utilisateur (whatsautoia@gmail.com) via Refresh Token
        Priorité 2 : Service Account (Fallback legacy)
        """
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        # --- 1. Tentative avec OAuth2 Utilisateur (whatsautoia@gmail.com) ---
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

        if client_id and client_secret and refresh_token:
            try:
                creds = Credentials(
                    token=None,
                    refresh_token=refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=scopes,
                )
                if not creds.valid:
                    creds.refresh(Request())
                return creds
            except Exception as e:
                print(f"⚠️ Échec de l'authentification OAuth2 Utilisateur : {e}")

        # --- 2. Fallback sur Service Account (Fichier local ou Variable d'environnement) ---
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        creds_path = os.path.join(base_dir, "credentials.json")

        if os.path.exists(creds_path):
            try:
                return ServiceAccountCredentials.from_service_account_file(
                    creds_path, scopes=scopes
                )
            except Exception as e:
                print(f"❌ Erreur lors du chargement de {creds_path} : {e}")

        creds_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_env:
            try:
                creds_dict = json.loads(creds_env)
                return ServiceAccountCredentials.from_service_account_info(
                    creds_dict, scopes=scopes
                )
            except Exception as e:
                print(f"❌ Erreur lors du parsing de GOOGLE_CREDENTIALS_JSON : {e}")

        return None

    @staticmethod
    def get_gspread_client():
        """Initialise le client gspread avec les credentials."""
        creds = SheetsService._get_google_credentials()
        if creds:
            try:
                return gspread.authorize(creds)
            except Exception as e:
                print(f"❌ Erreur lors de l'autorisation gspread : {e}")

        print("❌ Aucune méthode d'authentification Google valide trouvée.")
        return None

    @staticmethod
    def consolidate_and_get_catalog_sheet(spreadsheet):
        """Récupère l'onglet 'Catalogue' et assure une structure stricte des colonnes."""
        try:
            catalog_sheet = spreadsheet.worksheet("Catalogue")
        except gspread.exceptions.WorksheetNotFound:
            catalog_sheet = spreadsheet.add_worksheet(
                title="Catalogue", rows=100, cols=5
            )
            catalog_sheet.append_row(SheetsService.HEADERS)

        legacy_sheet = None
        for sheet_name in ["Feuille 1", "Sheet1", "Feuille1"]:
            try:
                legacy_sheet = spreadsheet.worksheet(sheet_name)
                break
            except gspread.exceptions.WorksheetNotFound:
                continue

        if legacy_sheet:
            records = legacy_sheet.get_all_records()
            if records:
                aligned_rows = []
                for rec in records:
                    norm_rec = {str(k).strip().lower(): v for k, v in rec.items()}
                    aligned_rows.append([
                        norm_rec.get("nom", ""),
                        norm_rec.get("description", ""),
                        norm_rec.get("prix", 0),
                        norm_rec.get("stock", 0),
                        norm_rec.get("image_url", ""),
                    ])

                catalog_sheet.clear()
                catalog_sheet.append_row(SheetsService.HEADERS)
                if aligned_rows:
                    catalog_sheet.append_rows(aligned_rows)
                print(f"✅ Données migrées de '{legacy_sheet.title}' vers 'Catalogue'.")

            try:
                spreadsheet.del_worksheet(legacy_sheet)
                print(f"🗑️ Onglet obsolète '{legacy_sheet.title}' supprimé.")
            except Exception as e:
                print(f"⚠️ Erreur suppression onglet '{legacy_sheet.title}' : {e}")

        return catalog_sheet

    @staticmethod
    def fetch_catalog(sheets_id):
        """Récupère le catalogue de produits depuis Google Sheets."""
        if not sheets_id or sheets_id == "ID_DU_GOOGLE_SHEETS_CLIENT":
            print("⚠️ Aucun ID Google Sheets valide configuré pour ce tenant.")
            return []

        try:
            client = SheetsService.get_gspread_client()
            if not client:
                return []

            spreadsheet = client.open_by_key(sheets_id)
            sheet = SheetsService.consolidate_and_get_catalog_sheet(spreadsheet)

            records = sheet.get_all_records()
            products = []
            for row in records:
                normalized_row = {
                    str(k).strip().lower(): str(v).strip()
                    for k, v in row.items()
                    if k
                }
                products.append(normalized_row)

            return products

        except Exception as e:
            print(f"❌ Erreur récupération catalogue Sheets : {str(e)}")
            return []

    @staticmethod
    def append_order(sheets_id, row_data):
        """Ajoute une commande dans l'onglet 'Commandes'."""
        try:
            client = SheetsService.get_gspread_client()
            if not client:
                return False

            spreadsheet = client.open_by_key(sheets_id)
            sheet_name = "Commandes"

            try:
                sheet = spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                sheet = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=7)
                headers = [
                    "Date",
                    "Téléphone Client",
                    "Nom Client",
                    "Adresse / Livraison",
                    "Articles Commandés",
                    "Total (DH)",
                    "Statut",
                ]
                sheet.append_row(headers)

            sheet.append_row(row_data)
            return True

        except Exception as e:
            print(f"❌ Erreur écriture commande Sheets : {repr(e)}")
            return False

    @staticmethod
    def create_store_sheet(store_name, vendor_email=None):
        """
        Crée un Google Sheet pour une nouvelle boutique au nom du compte whatsautoia@gmail.com.
        """
        try:
            creds = SheetsService._get_google_credentials()
            if not creds:
                print("❌ Credentials Google introuvables.")
                return None

            if not creds.valid:
                creds.refresh(Request())

            client = gspread.authorize(creds)
            title = f"WhatsAuto IA - {store_name}"[:100]
            folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
            template_id = os.getenv("GOOGLE_SHEETS_TEMPLATE_ID")

            headers = {
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json",
            }

            if template_id and folder_id:
                # 1. Duplication du modèle dans le dossier Drive dédié
                copy_url = f"https://www.googleapis.com/drive/v3/files/{template_id}/copy?supportsAllDrives=true"
                body = {
                    "name": title,
                    "parents": [folder_id]
                }
                res = requests.post(copy_url, headers=headers, json=body)

                if res.status_code != 200:
                    print(f"❌ Erreur lors de la copie du modèle ({res.status_code}) : {res.text}")
                    return None

                sheet_id = res.json().get("id")
                spreadsheet = client.open_by_key(sheet_id)
            else:
                # Fallback création directe gspread dans le dossier
                if folder_id:
                    spreadsheet = client.create(title, folder_id=folder_id)
                else:
                    spreadsheet = client.create(title)

            # 2. Configuration / Nettoyage de l'onglet Catalogue
            try:
                catalog_sheet = spreadsheet.worksheet("Catalogue")
            except gspread.exceptions.WorksheetNotFound:
                catalog_sheet = spreadsheet.sheet1
                catalog_sheet.update_title("Catalogue")

            catalog_sheet.clear()
            catalog_sheet.append_row(SheetsService.HEADERS)

            # 3. Configuration / Nettoyage de l'onglet Commandes
            try:
                commandes_sheet = spreadsheet.worksheet("Commandes")
            except gspread.exceptions.WorksheetNotFound:
                commandes_sheet = spreadsheet.add_worksheet(title="Commandes", rows=200, cols=7)

            commandes_sheet.clear()
            commandes_sheet.append_row([
                "Date", "Téléphone Client", "Nom Client",
                "Adresse / Livraison", "Articles Commandés", "Total (DH)", "Statut",
            ])

            # 4. Partage d'accès en écriture au vendeur (si renseigné et différent du propriétaire)
            if vendor_email:
                clean_email = str(vendor_email).strip().lower()
                if clean_email and clean_email != "whatsautoia@gmail.com":
                    try:
                        spreadsheet.share(clean_email, perm_type="user", role="writer")
                        print(f"📧 Sheet partagé avec succès à l'adresse : {clean_email}")
                    except Exception as e:
                        print(f"⚠️ Sheet créé mais échec du partage avec {clean_email} : {e}")
                else:
                    print(f"ℹ️ Aucun partage externe nécessaire pour l'adresse : '{vendor_email}'")

            print(f"✅ Google Sheet configuré avec succès pour '{store_name}' (ID: {spreadsheet.id})")
            return spreadsheet.id

        except Exception as e:
            print(f"❌ Erreur lors de la création du Sheet pour '{store_name}' : {repr(e)}")
            return None

    @staticmethod
    def update_stock(sheets_id, product_name, quantity_ordered):
        """Déduit la quantité commandée du stock d'un produit."""
        try:
            client = SheetsService.get_gspread_client()
            if not client:
                return False

            spreadsheet = client.open_by_key(sheets_id)
            sheet = SheetsService.consolidate_and_get_catalog_sheet(spreadsheet)
            records = sheet.get_all_records()

            for idx, row in enumerate(records, start=2):
                name_in_sheet = str(row.get("nom", "")).strip().lower()
                if name_in_sheet == product_name.strip().lower():
                    current_stock = int(row.get("stock", 0))
                    new_stock = max(0, current_stock - int(quantity_ordered))
                    sheet.update_cell(idx, 4, new_stock)
                    print(f"📉 Stock mis à jour pour '{product_name}' : {current_stock} -> {new_stock}")
                    return True

            return False

        except Exception as e:
            print(f"❌ Erreur mise à jour stock : {repr(e)}")
            return False

    @staticmethod
    def add_or_update_product(
        sheets_id, product_name, description, price, stock, image_url
    ):
        """Ajoute ou met à jour un produit en réécrivant la ligne entière A:E."""
        try:
            client = SheetsService.get_gspread_client()
            if not client:
                return False

            spreadsheet = client.open_by_key(sheets_id)
            sheet = SheetsService.consolidate_and_get_catalog_sheet(spreadsheet)

            records = sheet.get_all_records()
            row_data = [product_name, description, price, stock, image_url]

            for idx, row in enumerate(records, start=2):
                if str(row.get("nom", "")).strip().lower() == product_name.strip().lower():
                    cell_range = f"A{idx}:E{idx}"
                    sheet.update(cell_range, [row_data])
                    print(f"✅ Produit '{product_name}' mis à jour !")
                    return True

            sheet.append_row(row_data)
            print(f"✅ Produit '{product_name}' ajouté !")
            return True

        except Exception as e:
            print(f"❌ Erreur mise à jour produit : {repr(e)}")
            return False