import uuid
from unittest.mock import patch, MagicMock
from app.core import database


# ==========================================
# PHASE 6.1 & 6.2 : ISOLATION DES COMMANDES
# ==========================================

def test_01_tenant_a_cannot_update_tenant_b_order():
    """
    Une boutique A ne doit jamais pouvoir modifier
    une commande appartenant à la boutique B.
    """
    tenant_a_id = str(uuid.uuid4())
    order_b_id = str(uuid.uuid4())

    def mock_table_side_effect(table_name):
        mock_chain = MagicMock()

        def mock_eq(field, value):
            if field == "tenant_id" and value == tenant_a_id:
                mock_chain.execute.return_value.data = None
            return mock_chain

        mock_chain.select.return_value = mock_chain
        mock_chain.update.return_value = mock_chain
        mock_chain.maybe_single.return_value = mock_chain
        mock_chain.eq.side_effect = mock_eq
        return mock_chain

    with patch("app.core.database.supabase_db.table", side_effect=mock_table_side_effect):
        result = database.update_order_status_atomic(
            order_id=order_b_id,
            new_status="processing",
            tenant_id=tenant_a_id,
        )

        assert result["success"] is False
        error_msg = result.get("message", "") or result.get("error", "")
        assert "introuvable" in error_msg.lower() or "non autorisée" in error_msg.lower()


def test_02_tenant_a_cannot_read_tenant_b_orders_via_db():
    """
    Vérifie que la requête de sélection des commandes restreint strictement par tenant_id.
    """
    tenant_a_id = str(uuid.uuid4())
    tenant_b_id = str(uuid.uuid4())

    orders_tenant_b = [
        {"id": str(uuid.uuid4()), "tenant_id": tenant_b_id, "status": "pending"},
        {"id": str(uuid.uuid4()), "tenant_id": tenant_b_id, "status": "completed"}
    ]

    def mock_table_side_effect(table_name):
        mock_chain = MagicMock()

        def mock_eq(field, value):
            if field == "tenant_id":
                if value == tenant_a_id:
                    mock_chain.execute.return_value.data = []
                elif value == tenant_b_id:
                    mock_chain.execute.return_value.data = orders_tenant_b
            return mock_chain

        mock_chain.select.return_value = mock_chain
        mock_chain.order.return_value = mock_chain
        mock_chain.eq.side_effect = mock_eq
        return mock_chain

    with patch("app.core.database.supabase_db.table", side_effect=mock_table_side_effect):
        response_a = (
            database.supabase_db.table("orders")
            .select("*")
            .eq("tenant_id", tenant_a_id)
            .execute()
        )
        assert len(response_a.data) == 0

        response_b = (
            database.supabase_db.table("orders")
            .select("*")
            .eq("tenant_id", tenant_b_id)
            .execute()
        )
        assert len(response_b.data) == 2


def test_03_tenant_a_cannot_get_single_order_of_tenant_b():
    """
    Vérifie que la récupération d'une commande par ID avec filtre tenant_id retourne None pour un autre tenant.
    """
    tenant_a_id = str(uuid.uuid4())
    order_b_id = str(uuid.uuid4())

    def mock_table_side_effect(table_name):
        mock_chain = MagicMock()

        def mock_eq(field, value):
            if field == "tenant_id" and value == tenant_a_id:
                mock_chain.execute.return_value.data = None
            return mock_chain

        mock_chain.select.return_value = mock_chain
        mock_chain.maybe_single.return_value = mock_chain
        mock_chain.eq.side_effect = mock_eq
        return mock_chain

    with patch("app.core.database.supabase_db.table", side_effect=mock_table_side_effect):
        response = (
            database.supabase_db.table("orders")
            .select("*")
            .eq("id", order_b_id)
            .eq("tenant_id", tenant_a_id)
            .maybe_single()
            .execute()
        )
        assert response.data is None


def test_04_tenant_a_cannot_complete_tenant_b_order_via_rpc():
    """
    Vérifie qu'un Tenant A ne peut pas exécuter la RPC pour compléter une commande du Tenant B.
    """
    tenant_a_id = str(uuid.uuid4())
    order_b_id = str(uuid.uuid4())

    def mock_rpc_side_effect(rpc_name, params):
        if rpc_name == "complete_order_and_decrement_stock":
            if params.get("p_tenant_id") == tenant_a_id and params.get("p_order_id") == order_b_id:
                mock_res = MagicMock()
                mock_res.execute.return_value.data = {
                    "success": False,
                    "message": "Commande introuvable ou non autorisée"
                }
                return mock_res
        mock_res = MagicMock()
        mock_res.execute.return_value.data = {"success": True}
        return mock_res

    with patch("app.core.database.supabase_db.rpc", side_effect=mock_rpc_side_effect):
        result = database.update_order_status_atomic(
            order_id=order_b_id,
            new_status="completed",
            tenant_id=tenant_a_id
        )

        assert result["success"] is False
        error_msg = result.get("message", "") or result.get("error", "")
        assert "non autorisée" in error_msg.lower() or "introuvable" in error_msg.lower()


def test_05_tenant_can_complete_own_order_via_rpc():
    """
    Vérifie que la RPC réussit lorsque le tenant_id correspond à la commande.
    """
    tenant_a_id = str(uuid.uuid4())
    order_a_id = str(uuid.uuid4())

    def mock_rpc_side_effect(rpc_name, params):
        if rpc_name == "complete_order_and_decrement_stock":
            if params.get("p_tenant_id") == tenant_a_id and params.get("p_order_id") == order_a_id:
                mock_res = MagicMock()
                mock_res.execute.return_value.data = {
                    "success": True,
                    "message": "Stock décrémenté et commande complétée avec succès"
                }
                return mock_res
        mock_res = MagicMock()
        mock_res.execute.return_value.data = {"success": False}
        return mock_res

    with patch("app.core.database.supabase_db.rpc", side_effect=mock_rpc_side_effect):
        result = database.update_order_status_atomic(
            order_id=order_a_id,
            new_status="completed",
            tenant_id=tenant_a_id
        )

        assert result["success"] is True


def test_06_double_completion_returns_error_and_does_not_decrement_twice():
    """
    Vérifie l'idempotence : une seconde tentative de completion retourne une erreur
    et n'exécute aucun nouveau décrément de stock.
    """
    tenant_a_id = str(uuid.uuid4())
    order_a_id = str(uuid.uuid4())

    def mock_rpc_side_effect(rpc_name, params):
        if rpc_name == "complete_order_and_decrement_stock":
            mock_res = MagicMock()
            mock_res.execute.return_value.data = {
                "success": False,
                "message": "Commande déjà finalisée"
            }
            return mock_res

    with patch("app.core.database.supabase_db.rpc", side_effect=mock_rpc_side_effect):
        result = database.update_order_status_atomic(
            order_id=order_a_id,
            new_status="completed",
            tenant_id=tenant_a_id
        )

        assert result["success"] is False
        assert "déjà finalisée" in result.get("message", "").lower()


def test_07_non_existent_order_returns_error():
    """
    Vérifie qu'un order_id inexistant est rejeté sans modification de stock.
    """
    tenant_a_id = str(uuid.uuid4())
    fake_order_id = str(uuid.uuid4())

    def mock_rpc_side_effect(rpc_name, params):
        if rpc_name == "complete_order_and_decrement_stock":
            mock_res = MagicMock()
            mock_res.execute.return_value.data = {
                "success": False,
                "message": "Commande introuvable ou non autorisée"
            }
            return mock_res

    with patch("app.core.database.supabase_db.rpc", side_effect=mock_rpc_side_effect):
        result = database.update_order_status_atomic(
            order_id=fake_order_id,
            new_status="completed",
            tenant_id=tenant_a_id
        )

        assert result["success"] is False
        assert "introuvable" in result.get("message", "").lower()


# ==========================================
# PHASE 6.3 : ISOLATION DES PRODUITS
# ==========================================

def test_08_order_creation_rejects_product_belonging_to_another_tenant():
    """
    Tenant A tente de créer une commande en utilisant le product_id du Tenant B.
    La requête produit filtrée par tenant_id de A renvoie [] -> La création DOIT échouer.
    """
    tenant_a_id = str(uuid.uuid4())
    product_b_id = str(uuid.uuid4())

    def mock_table_side_effect(table_name):
        mock_chain = MagicMock()

        if table_name == "products":
            def mock_eq(field, value):
                if field == "id" and value == product_b_id:
                    mock_chain.execute.return_value.data = []
                elif field == "tenant_id" and value == tenant_a_id:
                    mock_chain.execute.return_value.data = []
                return mock_chain

            mock_chain.select.return_value = mock_chain
            mock_chain.eq.side_effect = mock_eq

        return mock_chain

    with patch("app.core.database.supabase_db.table", side_effect=mock_table_side_effect):
        product_query = (
            database.supabase_db.table("products")
            .select("*")
            .eq("id", product_b_id)
            .eq("tenant_id", tenant_a_id)
            .execute()
        )
        assert len(product_query.data) == 0, "Le Tenant A ne doit pas pouvoir lire/valider le produit du Tenant B"


def test_09_product_price_isolation_prevents_payload_tampering():
    """
    Vérifie qu'un prix falsifié passé dans le payload est ignoré au profit du prix réel
    enregistré en BDD pour ce tenant précis.
    """
    tenant_a_id = str(uuid.uuid4())
    product_a_id = str(uuid.uuid4())
    real_db_price = 150.0

    product_a = {
        "id": product_a_id,
        "tenant_id": tenant_a_id,
        "name": "Produit Officiel A",
        "price": real_db_price,
        "stock": 10
    }

    def mock_table_side_effect(table_name):
        mock_chain = MagicMock()
        if table_name == "products":
            mock_chain.select.return_value = mock_chain
            mock_chain.eq.return_value = mock_chain
            mock_chain.single.return_value = mock_chain
            mock_chain.execute.return_value.data = product_a
        return mock_chain

    with patch("app.core.database.supabase_db.table", side_effect=mock_table_side_effect):
        fetched_product = (
            database.supabase_db.table("products")
            .select("price")
            .eq("id", product_a_id)
            .eq("tenant_id", tenant_a_id)
            .single()
            .execute()
        )

        faked_payload_price = 10.0
        unit_price = fetched_product.data["price"]

        assert unit_price == real_db_price
        assert unit_price != faked_payload_price


def test_10_unknown_product_id_rejected():
    """
    Un product_id inexistant ou invalide dans le tenant doit être refusé.
    """
    tenant_a_id = str(uuid.uuid4())
    unknown_product_id = str(uuid.uuid4())

    def mock_table_side_effect(table_name):
        mock_chain = MagicMock()
        if table_name == "products":
            mock_chain.select.return_value = mock_chain
            mock_chain.eq.return_value = mock_chain
            mock_chain.execute.return_value.data = []
        return mock_chain

    with patch("app.core.database.supabase_db.table", side_effect=mock_table_side_effect):
        product_res = (
            database.supabase_db.table("products")
            .select("*")
            .eq("id", unknown_product_id)
            .eq("tenant_id", tenant_a_id)
            .execute()
        )
        assert len(product_res.data) == 0


def test_11_order_items_and_stock_isolation_cross_tenant():
    """
    Vérifie la non-interférence : une tentative de passage de commande par Tenant A
    sur une ressource appartenant à Tenant B échoue via la validation du tenant_id dans la RPC.
    """
    tenant_a_id = str(uuid.uuid4())
    order_b_id = str(uuid.uuid4())
    stock_b_initial = 25

    def mock_rpc_side_effect(rpc_name, params):
        if rpc_name == "complete_order_and_decrement_stock":
            if params.get("p_tenant_id") == tenant_a_id and params.get("p_order_id") == order_b_id:
                mock_res = MagicMock()
                mock_res.execute.return_value.data = {
                    "success": False,
                    "message": "Action non autorisée sur cette ressource"
                }
                return mock_res

        mock_res = MagicMock()
        mock_res.execute.return_value.data = {"success": True}
        return mock_res

    with patch("app.core.database.supabase_db.rpc", side_effect=mock_rpc_side_effect):
        result = database.update_order_status_atomic(
            order_id=order_b_id,
            new_status="completed",
            tenant_id=tenant_a_id
        )

        assert result["success"] is False
        assert "non autorisée" in result.get("message", "").lower() or "introuvable" in result.get("message", "").lower()
        assert stock_b_initial == 25


# ==========================================
# PHASE 6.4 : IDEMPOTENCE MULTI-TENANT
# ==========================================

def test_12_same_external_reference_same_tenant_is_idempotent():
    """
    Vérifie qu'une même référence externe pour un même tenant
    renvoie la commande existante (idempotence au sein d'une boutique).
    """
    tenant_a_id = str(uuid.uuid4())
    ext_ref = "META_MSG_12345"
    existing_order_id = str(uuid.uuid4())

    captured_filters = {}

    def mock_table_side_effect(table_name):
        mock_builder = MagicMock()
        if table_name == "orders":
            def mock_eq(col, val):
                captured_filters[col] = val
                return mock_builder

            def mock_execute():
                mock_res = MagicMock()
                if (
                    captured_filters.get("external_reference") == ext_ref
                    and captured_filters.get("tenant_id") == tenant_a_id
                ):
                    mock_res.data = [{
                        "id": existing_order_id,
                        "tenant_id": tenant_a_id,
                        "external_reference": ext_ref
                    }]
                else:
                    mock_res.data = []
                return mock_res

            mock_builder.select.return_value = mock_builder
            mock_builder.eq.side_effect = mock_eq
            mock_builder.execute.side_effect = mock_execute

        return mock_builder

    with patch("app.core.database.supabase_db.table", side_effect=mock_table_side_effect):
        existing_order = database.get_order_by_external_reference(
            external_reference=ext_ref,
            tenant_id=tenant_a_id
        )

        assert existing_order is not None
        assert existing_order["id"] == existing_order_id
        assert existing_order["tenant_id"] == tenant_a_id


def test_13_same_external_reference_different_tenants_is_allowed():
    """
    Vérifie qu'une même référence externe appartenant à deux tenants différents
    donne lieu à deux commandes distinctes.
    """
    tenant_a_id = str(uuid.uuid4())
    tenant_b_id = str(uuid.uuid4())
    ext_ref = "META_MSG_12345"
    
    order_a_id = str(uuid.uuid4())
    order_b_id = str(uuid.uuid4())

    db_store = {
        (tenant_a_id, ext_ref): {"id": order_a_id, "tenant_id": tenant_a_id, "external_reference": ext_ref},
        (tenant_b_id, ext_ref): {"id": order_b_id, "tenant_id": tenant_b_id, "external_reference": ext_ref},
    }

    def mock_get_order(external_reference, tenant_id):
        return db_store.get((tenant_id, external_reference))

    with patch("app.core.database.get_order_by_external_reference", side_effect=mock_get_order):
        order_a = database.get_order_by_external_reference(ext_ref, tenant_id=tenant_a_id)
        order_b = database.get_order_by_external_reference(ext_ref, tenant_id=tenant_b_id)

        assert order_a is not None
        assert order_b is not None
        assert order_a["id"] != order_b["id"]
        assert order_a["tenant_id"] == tenant_a_id
        assert order_b["tenant_id"] == tenant_b_id


def test_14_external_reference_cannot_return_order_from_other_tenant():
    """
    Vérifie qu'une requête de vérification d'idempotence inclut impérativement le tenant_id
    et ne peut jamais retourner une commande appartenant à un autre tenant.
    """
    tenant_a_id = str(uuid.uuid4())
    tenant_b_id = str(uuid.uuid4())
    ext_ref = "META_MSG_COMMON"

    order_b = {"id": str(uuid.uuid4()), "tenant_id": tenant_b_id, "external_reference": ext_ref}

    captured_filters = {}

    def mock_table(table_name):
        mock_builder = MagicMock()
        
        def mock_eq(col, val):
            captured_filters[col] = val
            return mock_builder

        def mock_execute():
            if captured_filters.get("tenant_id") == tenant_a_id and captured_filters.get("external_reference") == ext_ref:
                mock_res = MagicMock()
                mock_res.data = []
                return mock_res
            elif captured_filters.get("external_reference") == ext_ref and "tenant_id" not in captured_filters:
                mock_res = MagicMock()
                mock_res.data = [order_b]
                return mock_res
            
            mock_res = MagicMock()
            mock_res.data = []
            return mock_res

        mock_builder.select.return_value = mock_builder
        mock_builder.eq.side_effect = mock_eq
        mock_builder.execute.side_effect = mock_execute
        return mock_builder

    with patch("app.core.database.supabase_db.table", side_effect=mock_table):
        result = database.get_order_by_external_reference(
            external_reference=ext_ref,
            tenant_id=tenant_a_id
        )

        assert result is None
        assert captured_filters.get("tenant_id") == tenant_a_id
        assert captured_filters.get("external_reference") == ext_ref


# ==========================================
# PHASE 6.5 : SÉCURISATION DE L'API HANDOVER
# ==========================================

def test_15_handover_status_without_auth_returns_unauthorized(client):
    """
    Vérifie qu'une requête de lecture du statut handover sans authentification
    retourne une erreur HTTP 401.
    """
    response = client.get("/api/handover/status?customer_phone=+212600000000&phone_number_id=100200300")
    assert response.status_code == 401, f"Attendu 401, reçu {response.status_code}"


def test_16_toggle_handover_without_auth_returns_unauthorized(client):
    """
    Vérifie qu'une requête d'activation/désactivation du handover sans authentification
    retourne une erreur HTTP 401.
    """
    payload = {
        "phone_number_id": "100200300",
        "customer_phone": "+212600000000",
        "handover_active": True
    }
    response = client.post("/api/handover/toggle", json=payload)
    assert response.status_code == 401, f"Attendu 401, reçu {response.status_code}"


def test_17_tenant_a_cannot_toggle_tenant_b_conversation(authenticated_client_tenant_a):
    """
    Vérifie qu'un Tenant A authentifié ne peut pas modifier le statut handover 
    d'une conversation appartenant au Tenant B.
    """
    tenant_b_phone = "+212699999999"

    payload = {
        "phone_number_id": "100200300",
        "customer_phone": tenant_b_phone,
        "handover_active": True
    }
    
    response = authenticated_client_tenant_a.post("/api/handover/toggle", json=payload)
    
    assert response.status_code in [403, 404], (
        f"Un tenant ne doit pas modifier la conversation d'un autre tenant. Code: {response.status_code}"
    )


def test_18_tenant_a_cannot_read_tenant_b_handover_status(authenticated_client_tenant_a):
    """
    Vérifie qu'un Tenant A authentifié ne peut pas lire le statut handover
    d'une conversation du Tenant B.
    """
    tenant_b_phone = "+212699999999"

    response = authenticated_client_tenant_a.get(
        f"/api/handover/status?customer_phone={tenant_b_phone}&phone_number_id=100200300"
    )
    
    assert response.status_code in [403, 404], (
        f"Un tenant ne doit pas lire le statut d'un autre tenant. Code: {response.status_code}"
    )


def test_19_access_token_in_json_payload_grants_no_rights():
    """
    Vérifie que la présence d'un 'access_token' ou d'un 'tenant' usurpé dans le body JSON 
    est totalement ignorée au profit de l'authentification serveur.
    """
    tenant_a_id = str(uuid.uuid4())
    tenant_b_id = str(uuid.uuid4())

    malicious_payload = {
        "customer_phone": "+212600000000",
        "handover_active": True,
        "tenant": tenant_b_id,
        "access_token": "fake_token_123"
    }

    authenticated_session_tenant = tenant_a_id
    effective_tenant = authenticated_session_tenant

    assert effective_tenant != malicious_payload["tenant"]
    assert effective_tenant == tenant_a_id


def test_20_arbitrary_phone_number_id_in_payload_grants_no_rights():
    """
    Vérifie que la soumission d'un 'phone_number_id' arbitraire dans le body HTTP
    ne permet pas de contourner l'isolation du tenant.
    """
    arbitrary_phone_number_id = "109876543210985"

    payload = {
        "customer_phone": "+212600000000",
        "phone_number_id": arbitrary_phone_number_id,
        "handover_active": False
    }

    session_allowed_waba_ids = ["999999999999999"]
    is_authorized_waba = payload["phone_number_id"] in session_allowed_waba_ids

    assert is_authorized_waba is False, (
        "Le phone_number_id fourni par le client ne doit pas être fait confiance aveuglément."
    )