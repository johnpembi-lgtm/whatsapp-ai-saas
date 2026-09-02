import pytest
import uuid
import os
from postgrest.exceptions import APIError
from app.core.database import supabase_db, get_anon_supabase_client


@pytest.fixture
def multi_tenant_fixture():
    """Prépare un environnement isolé avec 2 tenants distincts et leurs données associées."""
    # 1. Tenant A
    tA_res = supabase_db.table("tenants").insert({
        "name": "Entreprise A",
        "whatsapp_phone_number_id": f"wa_A_{uuid.uuid4().hex[:6]}"
    }).execute()
    tenant_A = tA_res.data[0]

    # 2. Tenant B
    tB_res = supabase_db.table("tenants").insert({
        "name": "Entreprise B",
        "whatsapp_phone_number_id": f"wa_B_{uuid.uuid4().hex[:6]}"
    }).execute()
    tenant_B = tB_res.data[0]

    # 3. Données Tenant A
    cA = supabase_db.table("customers").insert({"tenant_id": tenant_A["id"], "phone": "212600000001"}).execute().data[0]
    convA = supabase_db.table("conversations").insert({"tenant_id": tenant_A["id"], "customer_id": cA["id"]}).execute().data[0]

    # 4. Données Tenant B
    cB = supabase_db.table("customers").insert({"tenant_id": tenant_B["id"], "phone": "212600000002"}).execute().data[0]
    convB = supabase_db.table("conversations").insert({"tenant_id": tenant_B["id"], "customer_id": cB["id"]}).execute().data[0]

    yield {
        "tenant_A": tenant_A,
        "tenant_B": tenant_B,
        "customer_A": cA,
        "customer_B": cB,
        "conv_A": convA,
        "conv_B": convB,
    }

    # Nettoyage global
    supabase_db.table("tenants").delete().in_("id", [tenant_A["id"], tenant_B["id"]]).execute()


# --- TEST 1 : ACCÈS ANONYME / NON AUTHENTIFIÉ (READ) ---
def test_anon_client_cannot_read_tenant_data(multi_tenant_fixture):
    """Vérifie qu'un client anonyme ne peut lire aucune donnée de tenant."""
    anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    if not anon_key or "votre_cle" in anon_key:
        pytest.skip("⚠️ SUPABASE_ANON_KEY non configurée dans le fichier .env")

    anon_client = get_anon_supabase_client()

    try:
        res_customers = anon_client.table("customers").select("*").execute()
        assert len(res_customers.data) == 0, "🚨 Faille RLS : Accès anonyme en lecture réussi !"
    except APIError as exc:
        assert exc.code in [401, "401", 403, "403", 42501] or "Invalid API key" in str(exc)


# --- TEST 2 : ACCÈS ANONYME / NON AUTHENTIFIÉ (WRITE / INJECTION) ---
def test_anon_client_cannot_write_tenant_data(multi_tenant_fixture):
    """Vérifie qu'un client anonyme ne peut pas insérer de données pour un tenant."""
    anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    if not anon_key or "votre_cle" in anon_key:
        pytest.skip("⚠️ SUPABASE_ANON_KEY non configurée dans le fichier .env")

    anon_client = get_anon_supabase_client()
    tA_id = multi_tenant_fixture["tenant_A"]["id"]

    try:
        anon_client.table("customers").insert({"tenant_id": tA_id, "phone": "212699999999"}).execute()
        pytest.fail("🚨 Faille RLS : Un client anonyme a réussi à insérer un client !")
    except APIError as exc:
        assert exc.code in [401, "401", 403, "403", 42501] or "Invalid API key" in str(exc) or "permission denied" in str(exc).lower()


# --- TEST 3 : ISOLATION STRICTE PAR TENANT_ID (SERVICE ROLE) ---
def test_service_role_maintains_full_isolation_and_access(multi_tenant_fixture):
    """Vérifie le cloisonnement logique strict entre Tenant A et Tenant B."""
    tA_id = multi_tenant_fixture["tenant_A"]["id"]
    tB_id = multi_tenant_fixture["tenant_B"]["id"]

    # ISOLEMENT READ
    customers_A = supabase_db.table("customers").select("*").eq("tenant_id", tA_id).execute().data
    customers_B = supabase_db.table("customers").select("*").eq("tenant_id", tB_id).execute().data

    assert len(customers_A) == 1
    assert customers_A[0]["phone"] == "212600000001"
    assert len(customers_B) == 1
    assert customers_B[0]["phone"] == "212600000002"

    # Vérification d'absence de fuite croisée
    assert customers_A[0]["id"] != customers_B[0]["id"]


# --- TEST 4 : EMBARGO DE CROSS-MODIFICATION / UPDATE ---
def test_prevent_cross_tenant_update(multi_tenant_fixture):
    """Vérifie qu'une modification ciblant explicitement Tenant A n'affecte jamais Tenant B."""
    tA_id = multi_tenant_fixture["tenant_A"]["id"]
    cB_id = multi_tenant_fixture["customer_B"]["id"]

    # Tentative de modifier le client de B sous le scope du Tenant A
    res = supabase_db.table("customers").update({"full_name": "Pirate User"}).eq("id", cB_id).eq("tenant_id", tA_id).execute()

    # Aucune ligne ne doit être modifiée
    assert len(res.data) == 0

    # Vérification que la donnée originelle de B est intacte
    check_cB = supabase_db.table("customers").select("*").eq("id", cB_id).execute().data[0]
    assert check_cB["full_name"] is None


# --- TEST 5 : EMBARGO DE CROSS-SUPPRESSION / DELETE ---
def test_prevent_cross_tenant_delete(multi_tenant_fixture):
    """Vérifie qu'une tentative de suppression par Tenant A ne détruit pas les données de Tenant B."""
    tA_id = multi_tenant_fixture["tenant_A"]["id"]
    cB_id = multi_tenant_fixture["customer_B"]["id"]

    # Tentative de suppression du client de B via un filtre Tenant A
    res = supabase_db.table("customers").delete().eq("id", cB_id).eq("tenant_id", tA_id).execute()

    # Le retour doit être vide
    assert len(res.data) == 0

    # Vérification de présence du client B
    check_cB = supabase_db.table("customers").select("*").eq("id", cB_id).execute().data
    assert len(check_cB) == 1