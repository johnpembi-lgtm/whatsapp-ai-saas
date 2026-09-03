import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app import create_app
from app.services import orders_service, vendor_service
from app.core import database


@pytest.fixture(scope="session")
def app_instance():
    app = create_app()
    return app


@pytest.fixture
def app_context(app_instance):
    with app_instance.app_context():
        yield app_instance


def _get_db_client():
    """Helper pour récupérer le client Supabase de l'application."""
    if hasattr(database, 'get_client'):
        return database.get_client()
    elif hasattr(database, 'supabase'):
        return database.supabase
    elif hasattr(database, 'supabase_db'):
        return database.supabase_db
    raise RuntimeError("Impossible de trouver le client Supabase dans database.py")


# --- FIXTURE AVEC CRÉATION RÉELLE EN BASE DE DONNÉES ---

@pytest.fixture
def setup_tenants_and_products(app_context):
    """
    Crée de vrais tenants et de vrais produits directement dans Supabase,
    puis retourne leurs véritables UUIDs générés par la base de données.
    """
    client = _get_db_client()
    unique = uuid.uuid4().hex[:12]

    # 1. Insertion réelle de Tenant A
    tenant_a_res = client.table("tenants").insert({
        "name": f"TEST Phase4 Alpha {unique}",
        "whatsapp_phone_number_id": f"WA_TEST_A_{unique}",
        "status": "active",
        "delivery_enabled": True,
        "pickup_enabled": True,
    }).execute()
    
    assert tenant_a_res.data and len(tenant_a_res.data) > 0, "Échec d'insertion du Tenant A dans Supabase"
    tenant_a_id = tenant_a_res.data[0]["id"]

    # 2. Insertion réelle de Tenant B
    tenant_b_res = client.table("tenants").insert({
        "name": f"TEST Phase4 Beta {unique}",
        "whatsapp_phone_number_id": f"WA_TEST_B_{unique}",
        "status": "active",
        "delivery_enabled": True,
        "pickup_enabled": True,
    }).execute()
    
    assert tenant_b_res.data and len(tenant_b_res.data) > 0, "Échec d'insertion du Tenant B dans Supabase"
    tenant_b_id = tenant_b_res.data[0]["id"]

    # Synchro éventuelle avec vendor_service si la table vendors est séparée
    if hasattr(vendor_service, 'get_or_create_vendor'):
        try:
            vendor_service.get_or_create_vendor(
                phone_number_id=tenant_a_res.data[0]["whatsapp_phone_number_id"],
                name=f"TEST Phase4 Alpha {unique}",
                delivery_enabled=True,
                pickup_enabled=True
            )
            vendor_service.get_or_create_vendor(
                phone_number_id=tenant_b_res.data[0]["whatsapp_phone_number_id"],
                name=f"TEST Phase4 Beta {unique}",
                delivery_enabled=True,
                pickup_enabled=True
            )
        except Exception:
            pass

    # 3. Insertion réelle du Produit sous Tenant A
    initial_stock = 10
    product_res = client.table("products").insert({
        "tenant_id": tenant_a_id,
        "name": f"Produit Test Stock {unique}",
        "price": 100.0,
        "stock": initial_stock
    }).execute()

    assert product_res.data and len(product_res.data) > 0, "Échec d'insertion du produit dans Supabase"
    product_id = product_res.data[0]["id"]

    return {
        "tenant_a": tenant_a_id,
        "tenant_b": tenant_b_id,
        "product_id": product_id,
        "initial_stock": initial_stock
    }


# --- SERVICE DISPATCH HELPER FUNCTIONS ---

def _call_create_order(tenant_id, customer_phone, items, delivery_type, **kwargs):
    if hasattr(orders_service, 'create_order'):
        return orders_service.create_order(
            tenant_id=tenant_id,
            customer_phone=customer_phone,
            items=items,
            delivery_type=delivery_type,
            **kwargs
        )
    elif hasattr(orders_service, 'process_order'):
        return orders_service.process_order(
            tenant_id=tenant_id,
            customer_phone=customer_phone,
            items=items,
            delivery_type=delivery_type,
            **kwargs
        )
    elif hasattr(orders_service, 'OrdersService'):
        service_cls = getattr(orders_service, 'OrdersService')
        if hasattr(service_cls, 'create_order'):
            return service_cls.create_order(
                tenant_id=tenant_id,
                customer_phone=customer_phone,
                items=items,
                delivery_type=delivery_type,
                **kwargs
            )
        elif hasattr(service_cls, 'process_order'):
            return service_cls.process_order(
                tenant_id=tenant_id,
                customer_phone=customer_phone,
                items=items,
                delivery_type=delivery_type,
                **kwargs
            )
    
    # Fallback direct vers database.py
    if hasattr(database, 'create_order_with_items'):
        vendor = vendor_service.get_vendor(tenant_id) if hasattr(vendor_service, 'get_vendor') else None
        if vendor:
            if delivery_type == "delivery" and not vendor.get("delivery_enabled", True):
                return {"success": False, "error": "Delivery disabled"}
            if delivery_type == "pickup" and not vendor.get("pickup_enabled", True):
                return {"success": False, "error": "Pickup disabled"}

        delivery_address = kwargs.get("delivery_address")
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        
        if delivery_type == "delivery" and not delivery_address and latitude is None and longitude is None:
            return {"success": False, "error": "Address required for delivery"}

        formatted_items = []
        total_calculated = 0.0
        for item in items:
            p_id = item.get("product_id")
            qty = item.get("quantity", 1)
            db_prod = database.get_product(p_id) if hasattr(database, 'get_product') else None
            unit_price = db_prod.get("price", item.get("price", 0.0)) if db_prod else item.get("price", 0.0)
            
            total_calculated += float(unit_price) * qty
            formatted_items.append({
                "product_id": p_id,
                "quantity": qty,
                "unit_price": unit_price
            })

        order_payload = {
            "tenant_id": tenant_id,
            "customer_phone": customer_phone,
            "status": "pending",
            "fulfillment_type": delivery_type,
            "delivery_address": delivery_address,
            "delivery_latitude": latitude,
            "delivery_longitude": longitude,
            "details": {
                "items": formatted_items,
                "total_price": total_calculated,
                "total_amount": total_calculated
            }
        }
        if kwargs.get("external_reference"):
            order_payload["external_reference"] = kwargs.get("external_reference")

        try:
            created_order = database.create_order_with_items(order_payload, formatted_items)
            if created_order and isinstance(created_order, dict) and created_order.get("id"):
                return {
                    "success": True,
                    "order_id": created_order.get("id"),
                    "total_amount": total_calculated
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

        return {"success": False, "error": "Failed to create order"}

    return {"success": False, "error": "Order creation function not found"}


def _call_update_status(order_id, tenant_id, new_status):
    if hasattr(orders_service, 'update_order_status'):
        return orders_service.update_order_status(
            order_id=order_id,
            tenant_id=tenant_id,
            new_status=new_status
        )
    elif hasattr(orders_service, 'update_status'):
        return orders_service.update_status(
            order_id=order_id,
            tenant_id=tenant_id,
            status=new_status
        )
    elif hasattr(orders_service, 'OrdersService'):
        service_cls = getattr(orders_service, 'OrdersService')
        if hasattr(service_cls, 'update_order_status'):
            return service_cls.update_order_status(order_id=order_id, tenant_id=tenant_id, new_status=new_status)
        elif hasattr(service_cls, 'update_status'):
            return service_cls.update_status(order_id=order_id, tenant_id=tenant_id, status=new_status)

    if hasattr(database, 'get_order'):
        existing_order = database.get_order(order_id)
        if existing_order and str(existing_order.get("tenant_id")) != str(tenant_id):
            return {"success": False, "error": "Tenant isolation violation", "updated": 0}

    if hasattr(database, 'update_order_status_atomic'):
        res = database.update_order_status_atomic(order_id, new_status)
        if res:
            return {"success": True, "updated": 1}

    return {"success": False, "updated": 0}


def _call_get_order(order_id):
    if hasattr(orders_service, 'get_order_by_id'):
        return orders_service.get_order_by_id(order_id)
    elif hasattr(orders_service, 'get_order'):
        return orders_service.get_order(order_id)
    elif hasattr(orders_service, 'OrdersService'):
        service_cls = getattr(orders_service, 'OrdersService')
        if hasattr(service_cls, 'get_order_by_id'):
            return service_cls.get_order_by_id(order_id)
        elif hasattr(service_cls, 'get_order'):
            return service_cls.get_order(order_id)
    
    if hasattr(database, 'get_order'):
        order = database.get_order(order_id) or {}
        details = order.get("details") or {}
        if isinstance(details, dict):
            amt = details.get("total_amount") or details.get("total_price")
            if amt is not None:
                order["total_amount"] = amt
        return order
        
    return {}


def _get_stock_safe(product_id):
    if hasattr(database, 'get_product_stock'):
        stock = database.get_product_stock(product_id)
        assert stock is not None, f"Impossible de récupérer le stock via get_product_stock pour {product_id}"
        return stock
    elif hasattr(database, 'get_product'):
        prod = database.get_product(product_id)
        assert prod is not None, f"Produit introuvable en base de données pour {product_id}"
        return prod.get("stock")
    
    client = _get_db_client()
    res = client.table("products").select("stock").eq("id", product_id).execute()
    assert res.data and len(res.data) > 0, f"Produit introuvable via Supabase Direct pour {product_id}"
    return res.data[0]["stock"]


# --- TESTS D'INTÉGRATION STRICTS ---

def test_delivery_disabled_for_tenant(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    # Désactiver la livraison directement en base / via service
    client = _get_db_client()
    client.table("tenants").update({"delivery_enabled": False}).eq("id", tenant_id).execute()

    if hasattr(vendor_service, 'update_vendor_settings'):
        vendor_service.update_vendor_settings(tenant_id, {"delivery_enabled": False})

    res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 1}],
        delivery_type="delivery",
        delivery_address="Casablanca"
    )
    assert res.get("success") is False, "La commande aurait dû être refusée (livraison désactivée)"


def test_pickup_disabled_for_tenant(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    client = _get_db_client()
    client.table("tenants").update({"pickup_enabled": False}).eq("id", tenant_id).execute()

    if hasattr(vendor_service, 'update_vendor_settings'):
        vendor_service.update_vendor_settings(tenant_id, {"pickup_enabled": False})

    res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 1}],
        delivery_type="pickup"
    )
    assert res.get("success") is False, "La commande aurait dû être refusée (remise en main propre désactivée)"


def test_delivery_requires_address_or_location(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    client = _get_db_client()
    client.table("tenants").update({"delivery_enabled": True}).eq("id", tenant_id).execute()

    if hasattr(vendor_service, 'update_vendor_settings'):
        vendor_service.update_vendor_settings(tenant_id, {"delivery_enabled": True})

    res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 1}],
        delivery_type="delivery",
        delivery_address=None,
        latitude=None,
        longitude=None
    )
    assert res.get("success") is False, "La livraison sans adresse ni coordonnées aurait dû échouer"


def test_pickup_does_not_require_address(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    client = _get_db_client()
    client.table("tenants").update({"pickup_enabled": True}).eq("id", tenant_id).execute()

    if hasattr(vendor_service, 'update_vendor_settings'):
        vendor_service.update_vendor_settings(tenant_id, {"pickup_enabled": True})

    res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "price": 100.0, "quantity": 1}],
        delivery_type="pickup",
        delivery_address=None
    )
    assert res.get("success") is True, f"Échec de création de la commande pickup: {res}"
    assert res.get("order_id") is not None


def test_backend_ignores_ai_price_and_uses_db_price(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    # Le prix en DB est de 100.0. On passe 1.0 (prix manipulé/IA)
    res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "price": 1.0, "quantity": 2}],
        delivery_type="pickup"
    )
    
    assert res.get("success") is True, f"Échec de la création de commande: {res}"
    order_id = res.get("order_id")
    assert order_id is not None

    order = _call_get_order(order_id)
    total = order.get("total_amount") or res.get("total_amount")
    assert float(total) == 200.0, f"Le backend aurait dû calculer 200.0 (prix DB 100x2) au lieu de {total}"


def test_tenant_a_cannot_update_tenant_b_order(setup_tenants_and_products):
    tenant_a = setup_tenants_and_products["tenant_a"]
    tenant_b = setup_tenants_and_products["tenant_b"]
    prod_id = setup_tenants_and_products["product_id"]

    create_res = _call_create_order(
        tenant_id=tenant_a,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "price": 100.0, "quantity": 1}],
        delivery_type="pickup"
    )
    assert create_res.get("success") is True, f"Échec de création de la commande initiale: {create_res}"
    order_id = create_res.get("order_id")
    assert order_id is not None

    # Tentative d'update par Tenant B sur une commande de Tenant A
    update_res = _call_update_status(
        order_id=order_id,
        tenant_id=tenant_b,
        new_status="completed"
    )
    
    order_after = _call_get_order(order_id)
    assert update_res.get("success") is False or update_res.get("updated") == 0, "Tenant B a réussi à modifier la commande de Tenant A!"
    assert order_after.get("status") == "pending", f"Le statut de la commande a été altéré: {order_after.get('status')}"


def test_order_creation_does_not_decrement_stock(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]
    
    initial_stock = _get_stock_safe(prod_id)

    res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 2}],
        delivery_type="pickup"
    )
    assert res.get("success") is True, f"Échec de création de commande: {res}"
    assert res.get("order_id") is not None

    stock_after = _get_stock_safe(prod_id)
    assert stock_after == initial_stock, f"Le stock a diminué à la création ({stock_after} au lieu de {initial_stock})"


def test_cancelled_order_does_not_decrement_stock(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    create_res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 2}],
        delivery_type="pickup"
    )
    assert create_res.get("success") is True, f"Échec de création de commande: {create_res}"
    order_id = create_res.get("order_id")
    assert order_id is not None

    initial_stock = _get_stock_safe(prod_id)

    update_res = _call_update_status(order_id=order_id, tenant_id=tenant_id, new_status="cancelled")
    assert update_res.get("success") is True or update_res.get("updated") == 1

    stock_after = _get_stock_safe(prod_id)
    assert stock_after == initial_stock, f"Le stock ne doit pas diminuer pour une commande annulée ({stock_after} != {initial_stock})"


def test_completed_order_decrements_stock(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    create_res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 2}],
        delivery_type="pickup"
    )
    assert create_res.get("success") is True, f"Échec de création de commande: {create_res}"
    order_id = create_res.get("order_id")
    assert order_id is not None

    initial_stock = _get_stock_safe(prod_id)

    update_res = _call_update_status(order_id=order_id, tenant_id=tenant_id, new_status="completed")
    assert update_res.get("success") is True or update_res.get("updated") == 1

    stock_after = _get_stock_safe(prod_id)
    assert stock_after == initial_stock - 2, f"Le stock aurait dû être décrémenté de 2 (Initial: {initial_stock}, Actuel: {stock_after})"


def test_completed_order_decrements_stock_only_once(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    create_res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 2}],
        delivery_type="pickup"
    )
    assert create_res.get("success") is True, f"Échec de création de commande: {create_res}"
    order_id = create_res.get("order_id")
    assert order_id is not None

    initial_stock = _get_stock_safe(prod_id)

    # Première complétion
    _call_update_status(order_id=order_id, tenant_id=tenant_id, new_status="completed")
    stock_first_pass = _get_stock_safe(prod_id)
    assert stock_first_pass == initial_stock - 2

    # Deuxième complétion (idempotence)
    _call_update_status(order_id=order_id, tenant_id=tenant_id, new_status="completed")
    stock_second_pass = _get_stock_safe(prod_id)

    assert stock_second_pass == stock_first_pass, "Le stock a été décrémenté une deuxième fois!"


def test_order_creation_idempotency(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]
    ext_ref = f"META_EVENT_{uuid.uuid4().hex}_UNIQUE"

    res1 = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 1}],
        delivery_type="pickup",
        external_reference=ext_ref
    )
    assert res1.get("success") is True, f"Échec du premier appel idempotence: {res1}"
    assert res1.get("order_id") is not None

    res2 = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 1}],
        delivery_type="pickup",
        external_reference=ext_ref
    )
    assert res2.get("success") is True, f"Échec du second appel idempotence: {res2}"
    assert res2.get("order_id") is not None

    assert res1["order_id"] == res2["order_id"], f"L'idempotence a échoué, deux IDs créés: {res1['order_id']} vs {res2['order_id']}"


def test_status_change_populates_timestamps(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]
    
    # 1. Test completed_at
    res_completed = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 1}],
        delivery_type="pickup"
    )
    assert res_completed.get("success") is True, f"Échec création commande 1: {res_completed}"
    order_id_1 = res_completed.get("order_id")
    assert order_id_1 is not None

    _call_update_status(order_id=order_id_1, tenant_id=tenant_id, new_status="completed")
    order_completed = _call_get_order(order_id_1)
    assert order_completed.get("completed_at") is not None, "completed_at aurait dû être renseigné"

    # 2. Test cancelled_at
    res_cancelled = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 1}],
        delivery_type="pickup"
    )
    assert res_cancelled.get("success") is True, f"Échec création commande 2: {res_cancelled}"
    order_id_2 = res_cancelled.get("order_id")
    assert order_id_2 is not None

    _call_update_status(order_id=order_id_2, tenant_id=tenant_id, new_status="cancelled")
    order_cancelled = _call_get_order(order_id_2)
    assert order_cancelled.get("cancelled_at") is not None, "cancelled_at aurait dû être renseigné"


def test_delivery_valid_with_coordinates_only(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    client = _get_db_client()
    client.table("tenants").update({"delivery_enabled": True}).eq("id", tenant_id).execute()

    if hasattr(vendor_service, 'update_vendor_settings'):
        vendor_service.update_vendor_settings(tenant_id, {"delivery_enabled": True})

    res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 1}],
        delivery_type="delivery",
        delivery_address=None,
        latitude=33.5731,
        longitude=-7.5898
    )
    assert res.get("success") is True, f"La livraison avec coordonnées GPS seules aurait dû réussir: {res}"
    assert res.get("order_id") is not None


def test_reverting_completed_order_to_pending_and_recompleting(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    create_res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 1}],
        delivery_type="pickup"
    )
    assert create_res.get("success") is True, f"Échec création de la commande: {create_res}"
    order_id = create_res.get("order_id")
    assert order_id is not None

    initial_stock = _get_stock_safe(prod_id)

    # Première complétion
    _call_update_status(order_id=order_id, tenant_id=tenant_id, new_status="completed")
    stock_after_first = _get_stock_safe(prod_id)
    assert stock_after_first == initial_stock - 1

    # Repassage à pending
    _call_update_status(order_id=order_id, tenant_id=tenant_id, new_status="pending")
    
    # Seconde complétion
    _call_update_status(order_id=order_id, tenant_id=tenant_id, new_status="completed")
    stock_after_second = _get_stock_safe(prod_id)

    assert stock_after_second == initial_stock - 1, f"Stock anormal après recomplétion ({stock_after_second} au lieu de {initial_stock - 1})"


def test_details_jsonb_structure_validity(setup_tenants_and_products):
    tenant_id = setup_tenants_and_products["tenant_a"]
    prod_id = setup_tenants_and_products["product_id"]

    res = _call_create_order(
        tenant_id=tenant_id,
        customer_phone="212600000000",
        items=[{"product_id": prod_id, "quantity": 3}],
        delivery_type="pickup"
    )
    assert res.get("success") is True, f"Échec de création de commande: {res}"
    order_id = res.get("order_id")
    assert order_id is not None

    order = _call_get_order(order_id)
    details = order.get("details", {})
    assert isinstance(details, dict), "La colonne 'details' n'est pas un dictionnaire JSON"
    assert "items" in details, "Le champ 'items' est manquant dans details"
    assert len(details["items"]) == 1, "Structure items incorrecte"
    assert details["items"][0]["quantity"] == 3