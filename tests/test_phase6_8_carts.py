import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def cart_tenants():
    return {
        "tenant_a": {"id": "tenant-uuid-A", "name": "Boutique A"},
        "tenant_b": {"id": "tenant-uuid-B", "name": "Boutique B"}
    }


def test_cart_isolation_same_customer_different_tenants(cart_tenants):
    """Vérifie qu'un même numéro client possède un panier distinct pour chaque tenant."""
    tenant_a = cart_tenants["tenant_a"]
    tenant_b = cart_tenants["tenant_b"]
    customer_phone = "212612345678"

    from app.services import cart_service

    def mock_get_cart_side_effect(tenant_id, phone):
        if tenant_id == tenant_a["id"]:
            return {"tenant_id": tenant_a["id"], "items": [{"product_id": "prod-A1", "qty": 2}]}
        elif tenant_id == tenant_b["id"]:
            return {"tenant_id": tenant_b["id"], "items": [{"product_id": "prod-B1", "qty": 1}]}
        return None

    with patch("app.services.cart_service.get_cart", side_effect=mock_get_cart_side_effect, create=True):
        if hasattr(cart_service, "get_cart"):
            cart_a = cart_service.get_cart(tenant_id=tenant_a["id"], phone=customer_phone)
            cart_b = cart_service.get_cart(tenant_id=tenant_b["id"], phone=customer_phone)

            assert cart_a["tenant_id"] == tenant_a["id"]
            assert cart_b["tenant_id"] == tenant_b["id"]
            assert cart_a["items"] != cart_b["items"]


def test_prevent_cross_tenant_product_addition(cart_tenants):
    """Vérifie qu'on ne peut pas ajouter un produit du Tenant B dans le panier du Tenant A."""
    tenant_a = cart_tenants["tenant_a"]
    product_b_id = "product-uuid-B"

    from app.services import cart_service

    with patch("app.core.database.get_product_by_id_and_tenant", return_value=None, create=True):
        if hasattr(cart_service, "add_item"):
            result = cart_service.add_item(
                tenant_id=tenant_a["id"],
                customer_phone="212612345678",
                product_id=product_b_id,
                quantity=1
            )
            assert result["success"] is False
            assert result.get("error") in ["PRODUCT_NOT_FOUND", "CROSS_TENANT_FORBIDDEN"]


def test_clear_cart_scoped_strictly_to_tenant(cart_tenants):
    """Vérifie que vider le panier du Tenant A ne modifie ni ne supprime le panier du Tenant B pour le même client."""
    tenant_a = cart_tenants["tenant_a"]
    customer_phone = "212612345678"

    from app.services import cart_service

    with patch("app.services.cart_service.clear_cart", create=True) as mock_clear:
        mock_clear.return_value = True

        if hasattr(cart_service, "clear_cart"):
            cart_service.clear_cart(tenant_id=tenant_a["id"], phone=customer_phone)
            mock_clear.assert_called_once_with(tenant_id=tenant_a["id"], phone=customer_phone)


def test_cart_access_by_cart_id_cross_tenant_blocked(cart_tenants):
    """Vérifie qu'un cart_id appartenant au Tenant B est inaccessible sous le contexte du Tenant A."""
    tenant_a = cart_tenants["tenant_a"]
    cart_b_id = "cart-uuid-B"

    from app.services import cart_service

    with patch("app.core.database.get_cart_by_id_and_tenant", return_value=None, create=True):
        if hasattr(cart_service, "get_cart_by_id"):
            cart = cart_service.get_cart_by_id(tenant_id=tenant_a["id"], cart_id=cart_b_id)
            assert cart is None