from unittest.mock import MagicMock, patch
from app.services.sheets_service import SheetsService


def test_fetch_catalog_cache():
    sheets_id = "sheet_test_999"

    # 1. On vide le dictionnaire de cache de la classe s'il existe
    if hasattr(SheetsService, "_catalog_cache"):
        SheetsService._catalog_cache.clear()

    # 2. Structure complète du produit pour éviter que le filtrage/nettoyage ne rejette l'élément
    mock_products = [
        {
            "nom": "Chemise",
            "description": "Belle chemise",
            "prix": "200",
            "stock": "10",
            "image_url": "http://example.com/img.jpg"
        }
    ]

    with patch.object(SheetsService, "get_gspread_client") as mock_gspread, \
         patch.object(SheetsService, "consolidate_and_get_catalog_sheet") as mock_consolidate:
        
        mock_spreadsheet = MagicMock()
        mock_sheet = MagicMock()
        mock_sheet.get_all_records.return_value = mock_products
        
        mock_gspread.return_value.open_by_key.return_value = mock_spreadsheet
        mock_consolidate.return_value = mock_sheet

        # Premier appel : Doit interroger l'API Google Sheets (call_count == 1)
        catalog_1 = SheetsService.fetch_catalog(sheets_id)
        
        # Vérification : S'assurer que le 1er appel n'a pas renvoyé une liste vide
        assert len(catalog_1) > 0, "Le catalogue renvoyé au 1er appel ne doit pas être vide"
        assert mock_gspread.call_count == 1

        # Second appel : Doit être servi par le cache sans incrémenter call_count
        catalog_2 = SheetsService.fetch_catalog(sheets_id)
        assert catalog_2 == catalog_1
        assert mock_gspread.call_count == 1