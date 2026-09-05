import time
from unittest.mock import MagicMock
import pytest
from app.core.tenant_manager import TenantManager


@pytest.fixture
def dummy_tenant():
    return {
        "id": "tenant-uuid-123",
        "name": "Boutique Test",
        "store_name": "Boutique Test",
        "whatsapp_phone_number_id": "100200300",
        "phone_number_id": "100200300",
        "is_active": True,
        "status": "active",
    }


def test_tenant_cache_hit_and_miss(mock_supabase_db, dummy_tenant):
    TenantManager.invalidate_cache()
    phone_id = "100200300"

    mock_response = MagicMock()
    mock_response.data = [dummy_tenant]
    mock_supabase_db.table().select().eq().execute.return_value = mock_response

    # 1. Premier appel : Miss -> Interrogation DB
    tenant_1 = TenantManager.get_tenant_by_phone_id(phone_id)
    assert tenant_1 is not None
    assert tenant_1["store_name"] == "Boutique Test"
    assert mock_supabase_db.table().select().eq().execute.call_count >= 1

    calls_before = mock_supabase_db.table().select().eq().execute.call_count

    # 2. Deuxième appel : Hit -> Doit venir du cache (pas de nouvel appel)
    tenant_2 = TenantManager.get_tenant_by_phone_id(phone_id)
    assert tenant_2["store_name"] == "Boutique Test"
    assert mock_supabase_db.table().select().eq().execute.call_count == calls_before


def test_tenant_cache_invalidation(mock_supabase_db, dummy_tenant):
    TenantManager.invalidate_cache()
    phone_id = "100200300"

    mock_response = MagicMock()
    mock_response.data = [dummy_tenant]
    mock_supabase_db.table().select().eq().execute.return_value = mock_response

    # Remplit le cache
    TenantManager.get_tenant_by_phone_id(phone_id)
    calls_first = mock_supabase_db.table().select().eq().execute.call_count

    # Invalide spécifiquement ce phone_id
    TenantManager.invalidate_cache(phone_id)

    # Ré-interroge : Supabase doit être de nouveau appelé
    TenantManager.get_tenant_by_phone_id(phone_id)
    assert mock_supabase_db.table().select().eq().execute.call_count > calls_first