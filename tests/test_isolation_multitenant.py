import pytest
from unittest.mock import patch, MagicMock
from app.core.tenant_manager import TenantManager

MOCK_TENANT_A = {
    "id": "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1",
    "phone_number_id": "1111111111",
    "store_name": "Boutique A",
    "sheets_id": "SHEET_A",
    "is_active": True
}

MOCK_TENANT_B = {
    "id": "b2b2b2b2-b2b2-b2b2-b2b2-b2b2b2b2b2b2",
    "phone_number_id": "2222222222",
    "store_name": "Boutique B",
    "sheets_id": "SHEET_B",
    "is_active": True
}


def test_tenant_resolution_isolation():
    """Vérifie que chaque phone_number_id résout uniquement son propre tenant_id."""
    with patch("app.core.tenant_manager.supabase") as mock_supabase:
        
        mock_query_a = MagicMock()
        mock_query_a.execute.return_value.data = [MOCK_TENANT_A]
        
        mock_query_b = MagicMock()
        mock_query_b.execute.return_value.data = [MOCK_TENANT_B]

        # Test Résolution Tenant A
        mock_supabase.table().select().eq().execute.side_effect = [mock_query_a.execute()]
        tenant_a = TenantManager.get_tenant_by_phone_id("1111111111")
        
        assert tenant_a is not None
        assert tenant_a["tenant_id"] == "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1"
        assert tenant_a["store_name"] == "Boutique A"
        assert tenant_a["sheets_id"] == "SHEET_A"

        # Test Résolution Tenant B
        mock_supabase.table().select().eq().execute.side_effect = [mock_query_b.execute()]
        tenant_b = TenantManager.get_tenant_by_phone_id("2222222222")
        
        assert tenant_b is not None
        assert tenant_b["tenant_id"] == "b2b2b2b2-b2b2-b2b2-b2b2-b2b2b2b2b2b2"
        assert tenant_b["store_name"] == "Boutique B"
        assert tenant_b["sheets_id"] == "SHEET_B"

        # Étanchéité stricts
        assert tenant_a["tenant_id"] != tenant_b["tenant_id"]
        assert tenant_a["sheets_id"] != tenant_b["sheets_id"]