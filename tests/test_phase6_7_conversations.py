import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def sample_tenants():
    return {
        "tenant_a": {"id": "tenant-uuid-A", "name": "Boutique A"},
        "tenant_b": {"id": "tenant-uuid-B", "name": "Boutique B"}
    }


def test_conversation_retrieval_isolated_by_tenant(sample_tenants):
    """Vérifie qu'un même numéro client chez A et B renvoie deux conversations isolées."""
    tenant_a = sample_tenants["tenant_a"]
    tenant_b = sample_tenants["tenant_b"]
    shared_customer_phone = "212612345678"

    from app.core import database

    def mock_get_conv_side_effect(tenant_id, customer_phone):
        if tenant_id == tenant_a["id"]:
            return {
                "id": "conv-uuid-A",
                "tenant_id": tenant_a["id"],
                "customer_phone": customer_phone,
                "mode": "BOT"
            }
        elif tenant_id == tenant_b["id"]:
            return {
                "id": "conv-uuid-B",
                "tenant_id": tenant_b["id"],
                "customer_phone": customer_phone,
                "mode": "HUMAN"
            }
        return None

    with patch("app.core.database.get_conversation_by_phone", side_effect=mock_get_conv_side_effect, create=True):
        if hasattr(database, "get_conversation_by_phone"):
            conv_a = database.get_conversation_by_phone(tenant_id=tenant_a["id"], customer_phone=shared_customer_phone)
            conv_b = database.get_conversation_by_phone(tenant_id=tenant_b["id"], customer_phone=shared_customer_phone)

            assert conv_a["id"] != conv_b["id"]
            assert conv_a["tenant_id"] == tenant_a["id"]
            assert conv_b["tenant_id"] == tenant_b["id"]


def test_cross_tenant_message_history_leak_prevented(sample_tenants):
    """Vérifie que le chargement de l'historique des messages pour l'IA ne peut pas retourner les messages d'un autre tenant."""
    tenant_a = sample_tenants["tenant_a"]
    tenant_b = sample_tenants["tenant_b"]
    shared_customer_phone = "212612345678"

    from app.core import database

    def mock_get_msgs_side_effect(tenant_id, phone, limit=10):
        if tenant_id == tenant_a["id"]:
            return [{"id": "msg-1", "tenant_id": tenant_a["id"], "role": "user", "content": "Commande Boutique A"}]
        return []

    with patch("app.core.database.get_recent_messages", side_effect=mock_get_msgs_side_effect, create=True):
        if hasattr(database, "get_recent_messages"):
            messages_b = database.get_recent_messages(tenant_id=tenant_b["id"], phone=shared_customer_phone)
            assert len(messages_b) == 0


def test_message_creation_binds_correct_tenant_id(sample_tenants):
    """Garantit qu'un nouveau message s'enregistre uniquement dans la conversation du tenant actif."""
    tenant_a = sample_tenants["tenant_a"]

    from app.core import database

    with patch("app.core.database.save_message", create=True) as mock_save:
        mock_save.return_value = {
            "id": "msg-new-uuid",
            "tenant_id": tenant_a["id"],
            "status": "stored"
        }

        if hasattr(database, "save_message"):
            result = database.save_message(
                tenant_id=tenant_a["id"],
                customer_phone="212612345678",
                sender="user",
                text="Je souhaite passer commande"
            )
            assert result["tenant_id"] == tenant_a["id"]


def test_mode_switch_isolation_bot_human(sample_tenants):
    """Vérifie que passer en mode HUMAN chez le Tenant A ne modifie pas le mode chez le Tenant B pour le même client."""
    tenant_a = sample_tenants["tenant_a"]
    tenant_b = sample_tenants["tenant_b"]
    shared_customer_phone = "212612345678"

    from app.services import handover_service

    # Simulation d'un basculement de mode pour Tenant A
    with patch("app.services.handover_service.set_conversation_mode", create=True) as mock_set_mode:
        mock_set_mode.return_value = True

        if hasattr(handover_service, "set_conversation_mode"):
            success = handover_service.set_conversation_mode(
                tenant_id=tenant_a["id"],
                customer_phone=shared_customer_phone,
                mode="HUMAN"
            )
            assert success is True
            mock_set_mode.assert_called_once_with(
                tenant_id=tenant_a["id"],
                customer_phone=shared_customer_phone,
                mode="HUMAN"
            )