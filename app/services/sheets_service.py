import csv
import io
import os
import gspread
import requests


class SheetsService:
    """Service pour interagir avec le catalogue et les commandes Google Sheets des boutiques."""

    HEADERS = ["nom", "description", "prix", "stock", "image_url"]

    @staticmethod
    def get_gspread_client():
        """Initialise le client gspread via le fichier de compte de service avec chemin absolu."""
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        creds_path = os.path.join(base_dir, "credentials.json")

        if not os.path.exists(creds_path):
            print(f"❌ Fichier de clés introuvable à : {creds_path}")
            return None

        return gspread.service_account(filename=creds_path)

    @classmethod
    def consolidate_and_get_catalog_sheet(cls, spreadsheet):
        """Récupère l'onglet 'Catalogue' et assure une structure stricte des colonnes."""
        try:
            catalog_sheet = spreadsheet.worksheet("Catalogue")
        except gspread.exceptions.WorksheetNotFound:
            catalog_sheet = spreadsheet.add_worksheet(
                title="Catalogue", rows=100, cols=5
            )
            catalog_sheet.append_row(cls.HEADERS)

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
                catalog_sheet.append_row(cls.HEADERS)
                if aligned_rows:
                    catalog_sheet.append_rows(aligned_rows)
                print(f"✅ Données migrées et réordonnées de '{legacy_sheet.title}' vers 'Catalogue'.")

            try:
                spreadsheet.del_worksheet(legacy_sheet)
                print(f"🗑️ Onglet obsolète '{legacy_sheet.title}' supprimé avec succès.")
            except Exception as e:
                print(f"⚠️ Impossible de supprimer l'onglet '{legacy_sheet.title}' : {e}")

        return catalog_sheet

    @classmethod
    def fetch_catalog(cls, sheets_id):
        """Récupère le catalogue de produits depuis Google Sheets."""
        if not sheets_id or sheets_id == "ID_DU_GOOGLE_SHEETS_CLIENT":
            print("⚠️ Aucun ID Google Sheets valide configuré pour ce tenant.")
            return []

        try:
            client = cls.get_gspread_client()
            if not client:
                return []

            spreadsheet = client.open_by_key(sheets_id)
            sheet = cls.consolidate_and_get_catalog_sheet(spreadsheet)

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

    @classmethod
    def update_stock(cls, sheets_id, product_name, quantity_ordered):
        """Déduit automatiquement la quantité commandée du stock d'un produit."""
        try:
            client = cls.get_gspread_client()
            if not client:
                return False

            spreadsheet = client.open_by_key(sheets_id)
            sheet = cls.consolidate_and_get_catalog_sheet(spreadsheet)
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

    @classmethod
    def add_or_update_product(
        cls, sheets_id, product_name, description, price, stock, image_url
    ):
        """Ajoute ou met à jour un produit en réécrivant TOUTE la ligne de A à E pour éviter tout décalage."""
        try:
            client = cls.get_gspread_client()
            if not client:
                return False

            spreadsheet = client.open_by_key(sheets_id)
            sheet = cls.consolidate_and_get_catalog_sheet(spreadsheet)

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