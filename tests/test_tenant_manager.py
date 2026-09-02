import time
from unittest.mock import MagicMock
from app.core.tenant_manager import TenantManager

def test_tenant_cache_hit_and_miss(mock_supabase_db, dummy_tenant):
    TenantManager.invalidate_cache()
    phone_id = "100200300"

    # Configuration du retour Supabase
    mock_response = MagicMock()
    mock_response.data = [dummy_tenant]
    mock_supabase_db.table().select().eq().execute.return_value = mock_response

    # 1. Premier appel : doit interroger Supabase (Miss)
    tenant_1 = TenantManager.get_tenant_by_phone_id(phone_id)
    assert tenant_1["store_name"] == "Boutique Test"
    assert mock_supabase_db.table().select().eq().execute.call_count == 1

    # 2. Deuxième appel : doit venir du cache mémoire (Hit -> pas de nouvel appel Supabase)
    tenant_2 = TenantManager.get_tenant_by_phone_id(phone_id)
    assert tenant_2["store_name"] == "Boutique Test"
    assert mock_supabase_db.table().select().eq().execute.call_count == 1

def test_tenant_cache_invalidation(mock_supabase_db, dummy_tenant):
    TenantManager.invalidate_cache()
    phone_id = "100200300"

    mock_response = MagicMock()
    mock_response.data = [dummy_tenant]
    mock_supabase_db.table().select().eq().execute.return_value = mock_response

    # Remplit le cache
    TenantManager.get_tenant_by_phone_id(phone_id)
    
    # Invalide spécifiquement ce phone_id
    TenantManager.invalidate_cache(phone_id)

    # Ré-interroge : Supabase doit être de nouveau appelé
    TenantManager.get_tenant_by_phone_id(phone_id)
    assert mock_supabase_db.table().select().eq().execute.call_count == 2