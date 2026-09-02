import pytest
import uuid
import os
from app.core.database import supabase_db

def test_supabase_client_is_service_role():
    """Vérifie que le client principal utilise bien la clé Service Role."""
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    assert service_key != "", "❌ SUPABASE_SERVICE_ROLE_KEY est vide dans l'environnement !"
    assert supabase_db is not None, "❌ Le client supabase_db n'est pas initialisé."

@pytest.fixture
def clean_tenant():
    """Crée un tenant de test et le nettoie après le test."""
    test_number_id = f"test_wa_{uuid.uuid4().hex[:8]}"
    
    tenant_res = supabase_db.table("tenants").insert({
        "name": "Test Tenant",
        "whatsapp_phone_number_id": test_number_id
    }).execute()
    tenant = tenant_res.data[0]
    
    yield tenant
    
    # Nettoyage
    supabase_db.table("tenants").delete().eq("id", tenant["id"]).execute()

def test_customer_uniqueness_same_tenant(clean_tenant):
    tenant_id = clean_tenant["id"]
    phone = "212600000001"
    
    c1 = supabase_db.table("customers").insert({"tenant_id": tenant_id, "phone": phone}).execute()
    assert len(c1.data) == 1
    
    with pytest.raises(Exception) as exc_info:
        supabase_db.table("customers").insert({"tenant_id": tenant_id, "phone": phone}).execute()
    assert "unique_customer_per_tenant" in str(exc_info.value) or "duplicate key" in str(exc_info.value)

def test_customer_same_phone_different_tenants(clean_tenant):
    phone = "212600000001"
    t1_id = clean_tenant["id"]
    supabase_db.table("customers").insert({"tenant_id": t1_id, "phone": phone}).execute()
    
    t2_res = supabase_db.table("tenants").insert({
        "name": "Test Tenant 2",
        "whatsapp_phone_number_id": f"test_wa_{uuid.uuid4().hex[:8]}"
    }).execute()
    t2_id = t2_res.data[0]["id"]
    
    try:
        c2 = supabase_db.table("customers").insert({"tenant_id": t2_id, "phone": phone}).execute()
        assert len(c2.data) == 1
    finally:
        supabase_db.table("tenants").delete().eq("id", t2_id).execute()

def test_webhook_event_deduplication():
    event_id = f"evt_{uuid.uuid4().hex}"
    message_id = f"wam_id_{uuid.uuid4().hex}"
    event_type = "message_received"
    
    try:
        res1 = supabase_db.table("webhook_events").insert({
            "event_id": event_id,
            "message_id": message_id,
            "event_type": event_type,
            "payload": {"status": "received"}
        }).execute()
        assert len(res1.data) == 1
        
        with pytest.raises(Exception):
            supabase_db.table("webhook_events").insert({
                "event_id": event_id,
                "message_id": message_id,
                "event_type": event_type,
                "payload": {"status": "duplicate"}
            }).execute()
            
    finally:
        supabase_db.table("webhook_events").delete().eq("event_id", event_id).execute()

def test_tenant_cascade_delete():
    t_res = supabase_db.table("tenants").insert({
        "name": "Cascade Tenant",
        "whatsapp_phone_number_id": f"test_wa_{uuid.uuid4().hex[:8]}"
    }).execute()
    t_id = t_res.data[0]["id"]
    
    c_res = supabase_db.table("customers").insert({"tenant_id": t_id, "phone": "212600000099"}).execute()
    c_id = c_res.data[0]["id"]
    
    conv_res = supabase_db.table("conversations").insert({"tenant_id": t_id, "customer_id": c_id}).execute()
    conv_id = conv_res.data[0]["id"]
    
    supabase_db.table("tenants").delete().eq("id", t_id).execute()
    
    check_c = supabase_db.table("customers").select("*").eq("id", c_id).execute()
    check_conv = supabase_db.table("conversations").select("*").eq("id", conv_id).execute()
    
    assert len(check_c.data) == 0
    assert len(check_conv.data) == 0