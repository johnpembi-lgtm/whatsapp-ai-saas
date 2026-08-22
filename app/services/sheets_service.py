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

        # Chercher la présence d'onglets legacy (Feuille 1 / Sheet1)
        legacy_sheet = None
        for sheet_name in ["Feuille 1", "Sheet1", "Feuille1"]:
            try:
                legacy_sheet = spreadsheet.worksheet(sheet_name)
                break
            except gspread.exceptions.WorksheetNotFound:
                continue

        # Migration intelligente et réordonnée
        if legacy_sheet:
            records = legacy_sheet.get_all_records()
            if records:
                # Reconstitution des lignes avec le bon ordre de colonnes
                aligned_rows = []
                for rec in records:
                    # Normalisation des clés
                    norm_rec = {str(k).strip().lower(): v for k, v in rec.items()}
                    aligned_rows.append([
                        norm_rec.get("nom", ""),
                        norm_rec.get("description", ""),
                        norm_rec.get("prix", 0),
                        norm_rec.get("stock", 0),
                        norm_rec.get("image_url", "")
                    ])
                
                # Écriture dans le catalogue propre
                catalog_sheet.clear()
                catalog_sheet.append_row(SheetsService.HEADERS)
                if aligned_rows:
                    catalog_sheet.append_rows(aligned_rows)
                print(f"✅ Données migrées et réordonnées de '{legacy_sheet.title}' vers 'Catalogue'.")

            try:
                spreadsheet.del_worksheet(legacy_sheet)
                print(f"🗑️ Onglet obsolète '{legacy_sheet.title}' supprimé avec succès.")
            except Exception as e:
                print(f"⚠️ Impossible de supprimer l'onglet '{legacy_sheet.title}' : {e}")

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
            print(f"❌ Erreur lors de la récupération du catalogue Sheets : {str(e)}")
            return []

    @staticmethod
    def append_order(sheets_id, row_data):
        """Vérifie l'existence de l'onglet 'Commandes', le crée si besoin, et ajoute la commande."""
        try:
            client = SheetsService.get_gspread_client()
            if not client:
                return False

            spreadsheet = client.open_by_key(sheets_id)
            sheet_name = "Commandes"

            try:
                sheet = spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                print(f"📄 Onglet '{sheet_name}' introuvable. Création automatique...")
                sheet = spreadsheet.add_worksheet(
                    title=sheet_name, rows=100, cols=7
                )
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
                print(f"✅ Onglet '{sheet_name}' créé avec succès !")

            sheet.append_row(row_data)
            return True

        except Exception as e:
            print(f"❌ Erreur lors de l'écriture dans Sheets : {repr(e)}")
            return False

    @staticmethod
    def create_store_sheet(store_name, vendor_email=None):
        """Crée un nouveau Google Sheet pour une boutique directement dans le dossier Drive partagé
        pour contourner la limite de quota du compte de service.
        """
        try:
            client = SheetsService.get_gspread_client()
            if not client:
                print("❌ Impossible de créer le Sheet : client Google indisponible.")
                return None

            title = f"WhatsAuto IA - {store_name}"[:100]
            folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

            if folder_id:
                # Appel direct de l'API Drive v3 avec la session d'authentification de gspread
                url = "https://www.googleapis.com/drive/v3/files"
                file_metadata = {
                    "name": title,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                    "parents": [folder_id],
                }
                res = client.auth.post(url, json=file_metadata)
                
                if res.status_code != 200:
                    print(f"❌ Erreur API Drive ({res.status_code}) : {res.text}")
                    return None

                sheet_id = res.json().get("id")
                spreadsheet = client.open_by_key(sheet_id)
            else:
                # Création standard en fallback
                spreadsheet = client.create(title)

            # Onglet Catalogue
            default_sheet = spreadsheet.sheet1
            default_sheet.update_title("Catalogue")
            default_sheet.append_row(SheetsService.HEADERS)

            # Onglet Commandes
            commandes_sheet = spreadsheet.add_worksheet(title="Commandes", rows=200, cols=7)
            commandes_sheet.append_row([
                "Date", "Téléphone Client", "Nom Client",
                "Adresse / Livraison", "Articles Commandés", "Total (DH)", "Statut",
            ])

            # Partage avec l'e-mail du vendeur si renseigné
            if vendor_email:
                try:
                    spreadsheet.share(vendor_email, perm_type="user", role="writer")
                except Exception as e:
                    print(f"⚠️ Sheet créé mais partage avec {vendor_email} échoué : {e}")

            print(f"✅ Nouveau Google Sheet créé pour '{store_name}' : {spreadsheet.id}")
            return spreadsheet.id

        except Exception as e:
            print(f"❌ Erreur lors de la création du Sheet pour '{store_name}' : {repr(e)}")
            return None

    @staticmethod
    def update_stock(sheets_id, product_name, quantity_ordered):
        """Déduit automatiquement la quantité commandée du stock d'un produit."""
        try:
            client = SheetsService.get_gspread_client()
            if not client:
                return False

            spreadsheet = client.open_by_key(sheets_id)
            sheet = SheetsService.consolidate_and_get_catalog_sheet(spreadsheet)
            records = sheet.get_all_records()

            for idx, row in enumerate(records, start=2):  # Line 1 = headers
                name_in_sheet = str(row.get("nom", "")).strip().lower()
                if name_in_sheet == product_name.strip().lower():
                    current_stock = int(row.get("stock", 0))
                    new_stock = max(0, current_stock - int(quantity_ordered))

                    # La colonne Stock est strictement la colonne D (Index 4)
                    sheet.update_cell(idx, 4, new_stock)
                    print(f"📉 Stock mis à jour pour '{product_name}' : {current_stock} -> {new_stock}")
                    return True

            print(f"⚠️ Produit '{product_name}' non trouvé dans le catalogue pour déduction.")
            return False

        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour du stock : {repr(e)}")
            return False

    @staticmethod
    def add_or_update_product(
        sheets_id, product_name, description, price, stock, image_url
    ):
        """Ajoute ou met à jour un produit en réécrivant TOUTE la ligne de A à E pour éviter tout décalage."""
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
                    # Met à jour d'un seul coup la plage A-E de la ligne
                    cell_range = f"A{idx}:E{idx}"
                    sheet.update(cell_range, [row_data])
                    print(f"✅ Produit '{product_name}' mis à jour proprement dans le catalogue Sheets !")
                    return True

            # Si nouveau produit
            sheet.append_row(row_data)
            print(f"✅ Nouveau produit '{product_name}' ajouté au catalogue Sheets !")
            return True

        except Exception as e:
            print(f"❌ Erreur lors de l'ajout/modification du produit dans Sheets : {repr(e)}")
            return False