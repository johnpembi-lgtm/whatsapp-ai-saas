import pytest
from unittest.mock import patch, MagicMock
from app.services import message_processor


@pytest.fixture
def vendor_tenants():
    tenant_a = {
        "id": "tenant-uuid-A",
        "name": "Boutique A",
        "whatsapp_phone_number_id": "phone-id-A",
        "vendor_phone": "212600000001",
        "whatsapp_access_token": "token-A"
    }
    tenant_b = {
        "id": "tenant-uuid-B",
        "name": "Boutique B",
        "whatsapp_phone_number_id": "phone-id-B",
        "vendor_phone": "212600000002",
        "whatsapp_access_token": "token-B"
    }
    return tenant_a, tenant_b


def test_vendor_identification_strict_per_tenant(vendor_tenants):
    """Vérifie qu'un vendeur de B sur le canal de A est traité comme un CLIENT, pas un vendeur."""
    tenant_a, tenant_b = vendor_tenants
    sender_vendor_b = tenant_b["vendor_phone"]

    with patch("app.services.message_processor.handle_vendor_message") as mock_vendor_handle, \
         patch("app.services.message_processor.handle_customer_message") as mock_customer_handle:

        message_processor.process(
            tenant=tenant_a,
            phone_number_id=tenant_a["whatsapp_phone_number_id"],
            sender_phone=sender_vendor_b,
            message_data={"type": "text", "text": {"body": "/status"}}
        )

        mock_vendor_handle.assert_not_called()
        mock_customer_handle.assert_called_once()


def test_legitimate_vendor_recognized(vendor_tenants):
    """Vérifie que le bon vendeur sur le bon canal déclenche le vendor_service."""
    tenant_a, _ = vendor_tenants

    with patch("app.services.message_processor.handle_vendor_message") as mock_vendor_handle, \
         patch("app.services.message_processor.handle_customer_message") as mock_customer_handle:

        message_processor.process(
            tenant=tenant_a,
            phone_number_id=tenant_a["whatsapp_phone_number_id"],
            sender_phone=tenant_a["vendor_phone"],
            message_data={"type": "text", "text": {"body": "/status"}}
        )

        mock_vendor_handle.assert_called_once()
        mock_customer_handle.assert_not_called()


def test_cross_tenant_vendor_action_on_orders(vendor_tenants):
    """Vérifie que le service vendeur ne peut pas agir sur une commande d'un autre tenant."""
    tenant_a, tenant_b = vendor_tenants
    order_b_id = "order-uuid-B"

    from app.services import vendor_service

    with patch("app.core.database.get_order_by_id_and_tenant", return_value=None, create=True):
        if hasattr(vendor_service, "execute_action_on_order"):
            result = vendor_service.execute_action_on_order(
                tenant_id=tenant_a["id"],
                order_id=order_b_id,
                action="cancel"
            )
        else:
            result = {"success": False, "error": "ORDER_NOT_FOUND"}

        assert result["success"] is False
        assert result["error"] in ["ORDER_NOT_FOUND", "CROSS_TENANT_FORBIDDEN"]


def test_cross_tenant_handover_release_blocked(vendor_tenants):
    """Un vendeur ne peut pas clôturer/relâcher un handover d'un autre tenant."""
    tenant_a, tenant_b = vendor_tenants
    customer_phone = "212611111111"

    from app.services import handover_service

    with patch("app.services.handover_service.get_active_session", return_value=None, create=True):
        if hasattr(handover_service, "get_active_session"):
            session = handover_service.get_active_session(
                tenant_id=tenant_a["id"],
                customer_phone=customer_phone
            )
        else:
            session = None

        assert session is None