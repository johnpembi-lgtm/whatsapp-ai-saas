import csv
import io
import json
import os
import gspread
import requests
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request


class SheetsService:
    """Service pour interagir avec le catalogue et les commandes Google Sheets des boutiques."""

    HEADERS = ["nom", "description", "prix", "stock", "image_url"]

    @staticmethod
    def _get_google_credentials():
        """Récupère et valide les objets Credentials Google OAuth2."""
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        creds_path = os.path.join(base_dir, "credentials.json")

        if os.path.exists(creds_path):
            try:
                return Credentials.from_service_account_file(creds_path, scopes=scopes)
            except Exception as e:
                print(f"❌ Erreur lors du chargement de {creds_path} : {e}")

        creds_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_env:
            try:
                creds_dict = json.loads(creds_env)
                return Credentials.from_service_account_info(creds_dict, scopes=scopes)
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
        Crée un Google Sheet via Sheets API v4, l'associe au dossier Drive partagé
        et octroie les droits d'accès à l'e-mail du vendeur.
        """
        try:
            creds = SheetsService._get_google_credentials()
            if not creds:
                print("❌ Credentials introuvables.")
                return None

            if not creds.valid:
                creds.refresh(Request())

            client = gspread.authorize(creds)
            title = f"WhatsAuto IA - {store_name}"[:100]
            folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

            # 1. Création via Sheets API v4 (Bypasse le quota 0 octet du Service Account)
            sheets_url = "https://sheets.googleapis.com/v4/spreadsheets"
            headers = {
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json",
            }
            body = {"properties": {"title": title}}

            res = requests.post(sheets_url, headers=headers, json=body)
            if res.status_code != 200:
                print(f"❌ Erreur API Sheets ({res.status_code}) : {res.text}")
                return None

            sheet_id = res.json().get("spreadsheetId")

            # 2. Déplacement du fichier créé vers le dossier Drive partagé
            if folder_id:
                drive_url = f"https://www.googleapis.com/drive/v3/files/{sheet_id}?addParents={folder_id}&supportsAllDrives=true"
                move_res = requests.patch(drive_url, headers=headers, json={})
                if move_res.status_code != 200:
                    print(f"⚠️ Échec du rattachement au dossier Drive : {move_res.text}")

            spreadsheet = client.open_by_key(sheet_id)

            # Structure initiale de la feuille
            default_sheet = spreadsheet.sheet1
            default_sheet.update_title("Catalogue")
            default_sheet.append_row(SheetsService.HEADERS)

            commandes_sheet = spreadsheet.add_worksheet(title="Commandes", rows=200, cols=7)
            commandes_sheet.append_row([
                "Date", "Téléphone Client", "Nom Client",
                "Adresse / Livraison", "Articles Commandés", "Total (DH)", "Statut",
            ])

            # 3. Partage d'accès en écriture à l'e-mail du vendeur
            if vendor_email:
                try:
                    spreadsheet.share(vendor_email, perm_type="user", role="writer")
                    print(f"📧 Sheet partagé avec succès à l'adresse : {vendor_email}")
                except Exception as e:
                    print(f"⚠️ Erreur partage avec {vendor_email} : {e}")

            print(f"✅ Google Sheet configuré pour '{store_name}' (ID: {spreadsheet.id})")
            return spreadsheet.id

        except Exception as e:
            print(f"❌ Erreur création Sheet '{store_name}' : {repr(e)}")
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