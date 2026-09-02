import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def dummy_tenant():
    return {
        "id": "tenant-uuid-123",
        "tenant_id": "tenant-uuid-123",
        "phone_number_id": "100200300",
        "store_id": "BoutiqueTest",
        "store_name": "Boutique Test",
        "vendor_phone": "212600000000",
        "sheets_id": "sheets_id_abc123",
        "system_prompt": "Tu es un assistant virtuel.",
        "is_active": True,
        "whatsapp_access_token": "fake_wa_token"
    }

@pytest.fixture
def mock_supabase_db(mocker):
    """Intercepte le client Supabase global de l'application."""
    mock_db = MagicMock()
    mocker.patch("app.core.database.supabase_db", mock_db)
    mocker.patch("app.core.tenant_manager.supabase", mock_db)
    mocker.patch("app.services.retargeting_service.supabase_db", mock_db)
    return mock_db