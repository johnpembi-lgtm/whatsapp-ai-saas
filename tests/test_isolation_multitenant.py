from unittest.mock import MagicMock, patch
from app.core.tenant_manager import TenantManager


def test_tenant_resolution_isolation():
    """Vérifie que chaque phone_number_id résout uniquement son propre tenant_id."""
    TenantManager.invalidate_cache()

    tenant_a = {
        "id": "tenant-uuid-A",
        "name": "Boutique A",
        "whatsapp_phone_number_id": "111111",
        "status": "active",
    }
    tenant_b = {
        "id": "tenant-uuid-B",
        "name": "Boutique B",
        "whatsapp_phone_number_id": "222222",
        "status": "active",
    }

    mock_db = MagicMock()

    def mock_eq(col, val):
        mock_exec = MagicMock()
        if val == "111111":
            mock_exec.execute.return_value.data = [tenant_a]
        elif val == "222222":
            mock_exec.execute.return_value.data = [tenant_b]
        else:
            mock_exec.execute.return_value.data = []
        return mock_exec

    mock_db.table().select().eq.side_effect = mock_eq

    with patch("app.core.database.supabase_db", mock_db):
        res_a = TenantManager.get_tenant_by_phone_id("111111")
        res_b = TenantManager.get_tenant_by_phone_id("222222")

        assert res_a is not None
        assert res_a["tenant_id"] == "tenant-uuid-A"

        assert res_b is not None
        assert res_b["tenant_id"] == "tenant-uuid-B"