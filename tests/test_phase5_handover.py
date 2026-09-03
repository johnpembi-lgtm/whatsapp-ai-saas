import pytest
from unittest.mock import MagicMock, patch

from app.services import handover_service
from app.services.vendor_service import handle_vendor_message
from app.services.customer_processor import handle_customer_message


@pytest.fixture
def mock_tenant_a():
    return {
        "id": "tenant-a-uuid",
        "phone_number_id": "PNID_SHOP_A",
        "vendor_phone": "212600000001",
        "sheets_id": "sheet_a_id",
    }


@pytest.fixture
def mock_tenant_b():
    return {
        "id": "tenant-b-uuid",
        "phone_number_id": "PNID_SHOP_B",
        "vendor_phone": "212600000002",
        "sheets_id": "sheet_b_id",
    }


# ============================================================================
# TESTS 1 À 5 : HANDOVER SERVICE & IDEMPOTENCE
# ============================================================================


def test_01_default_mode_is_bot():
    """1. Mode par défaut = BOT si aucune conversation enregistrée."""
    with patch("app.core.database.get_conversation_mode", return_value=None):
        mode = handover_service.get_mode("PNID_SHOP_A", "212611112222") or "bot"
        assert mode == "bot"


def test_02_transition_bot_to_human(mock_tenant_a):
    """2. Passage BOT -> HUMAN."""
    with patch("app.core.database.set_conversation_mode", return_value=True), patch(
        "app.services.whatsapp_service.WhatsAppService.send_message",
        return_value=True,
    ):
        success = handover_service.activate_human_mode(
            phone_number_id="PNID_SHOP_A",
            customer_phone="212611112222",
            tenant=mock_tenant_a,
            access_token="fake_token",
            trigger_message="Aide demandée",
        )
        assert success is True


def test_03_transition_human_to_bot():
    """3. Passage HUMAN -> BOT."""
    with patch("app.core.database.set_conversation_mode", return_value=True):
        success = handover_service.deactivate_human_mode("PNID_SHOP_A", "212611112222")
        assert success is True


def test_04_double_activation_human_is_idempotent(mock_tenant_a):
    """4. Double activation HUMAN = idempotente (ne plante pas)."""
    with patch("app.core.database.set_conversation_mode", return_value=True), patch(
        "app.services.whatsapp_service.WhatsAppService.send_message",
        return_value=True,
    ):
        res1 = handover_service.activate_human_mode(
            "PNID_SHOP_A", "212611112222", mock_tenant_a, "fake_token"
        )
        res2 = handover_service.activate_human_mode(
            "PNID_SHOP_A", "212611112222", mock_tenant_a, "fake_token"
        )
        assert res1 is True
        assert res2 is True


def test_05_double_deactivation_bot_is_idempotent():
    """5. Double retour BOT = idempotent."""
    with patch("app.core.database.set_conversation_mode", return_value=True):
        res1 = handover_service.deactivate_human_mode("PNID_SHOP_A", "212611112222")
        res2 = handover_service.deactivate_human_mode("PNID_SHOP_A", "212611112222")
        assert res1 is True
        assert res2 is True


# ============================================================================
# TESTS 6 À 9 : FLUX MESSAGES CLIENT & DELEGATION IA
# ============================================================================


def test_06_customer_message_saved_in_human_mode(mock_tenant_a):
    """6. Message client en HUMAN enregistré en base."""
    with patch(
        "app.services.customer_processor.handover_service.get_mode",
        return_value="human",
    ), patch(
        "app.services.customer_processor.database.get_conversation_history",
        return_value=[],
    ), patch(
        "app.services.customer_processor.database.save_message"
    ) as mock_save, patch(
        "app.services.customer_processor.AIService.generate_response"
    ) as mock_ai:

        handle_customer_message(
            phone_number_id="PNID_SHOP_A",
            sender_phone="212611112222",
            message_data={
                "type": "text",
                "text": {"body": "Bonjour vendeur !"},
            },
            tenant=mock_tenant_a,
            access_token="fake_token",
        )

        mock_save.assert_called_once_with(
            "PNID_SHOP_A",
            "212611112222",
            "user",
            "Bonjour vendeur !",
        )

        mock_ai.assert_not_called()


def test_07_ai_never_called_in_human_mode(mock_tenant_a):
    """7. IA jamais appelée si la conversation est en mode HUMAN."""
    with patch(
        "app.services.customer_processor.handover_service.get_mode",
        return_value="human",
    ), patch(
        "app.services.customer_processor.database.get_conversation_history",
        return_value=[],
    ), patch(
        "app.services.customer_processor.database.save_message"
    ), patch(
        "app.services.customer_processor.AIService.generate_response"
    ) as mock_ai:

        handle_customer_message(
            phone_number_id="PNID_SHOP_A",
            sender_phone="212611112222",
            message_data={
                "type": "text",
                "text": {"body": "Proposez-moi un produit"},
            },
            tenant=mock_tenant_a,
            access_token="fake_token",
        )

        mock_ai.assert_not_called()


def test_08_customer_message_processed_by_ai_in_bot_mode(mock_tenant_a):
    """8. Message client en BOT traité normalement avec réponse IA."""
    with patch(
        "app.services.customer_processor.handover_service.get_mode",
        return_value="bot",
    ), patch(
        "app.services.customer_processor.database.get_conversation_history",
        return_value=[],
    ), patch(
        "app.services.customer_processor.database.save_message"
    ), patch(
        "app.services.customer_processor.CartService.update_interaction"
    ), patch(
        "app.services.customer_processor.SheetsService.fetch_catalog",
        return_value=[],
    ), patch(
        "app.services.customer_processor.AIService.generate_response",
        return_value="Réponse IA",
    ) as mock_ai, patch(
        "app.services.customer_processor.WhatsAppService.send_message",
        return_value=True,
    ) as mock_send, patch(
        "app.services.customer_processor.OrdersService"
    ):

        handle_customer_message(
            phone_number_id="PNID_SHOP_A",
            sender_phone="212611112222",
            message_data={
                "type": "text",
                "text": {"body": "Quels sont vos prix ?"},
            },
            tenant=mock_tenant_a,
            access_token="fake_token",
        )

        mock_ai.assert_called_once()
        mock_send.assert_called()


def test_09_explicit_transfer_request_activates_human_mode(mock_tenant_a):
    """9. Demande explicite de transfert active HUMAN."""
    with patch(
        "app.services.customer_processor.handover_service.get_mode",
        return_value="bot",
    ), patch(
        "app.services.customer_processor.handover_service.is_transfer_requested",
        return_value=True,
    ), patch(
        "app.services.customer_processor.handover_service.activate_human_mode",
        return_value=True,
    ) as mock_activate, patch(
        "app.services.customer_processor.database.get_conversation_history",
        return_value=[],
    ), patch(
        "app.services.customer_processor.database.save_message"
    ), patch(
        "app.services.customer_processor.WhatsAppService.send_message",
        return_value=True,
    ):

        handle_customer_message(
            phone_number_id="PNID_SHOP_A",
            sender_phone="212611112222",
            message_data={
                "type": "text",
                "text": {"body": "Je veux parler à un humain"},
            },
            tenant=mock_tenant_a,
            access_token="fake_token",
        )

        mock_activate.assert_called_once()


# ============================================================================
# TESTS 10 À 12 : COMMANDES VENDEUR ET ISOLATION MULTI-TENANT
# ============================================================================


def test_10_vendor_identified_correctly(mock_tenant_a):
    """10. Vendeur identifié et commande /human exécutée."""
    with patch(
        "app.services.handover_service.activate_human_mode",
        return_value=True,
    ), patch(
        "app.services.whatsapp_service.WhatsAppService.send_message"
    ) as mock_send:

        handle_vendor_message(
            phone_number_id="PNID_SHOP_A",
            vendor_phone="212600000001",
            msg_type="text",
            message_data={"text": {"body": "/human 212611112222"}},
            tenant=mock_tenant_a,
            access_token="fake_token",
        )

        mock_send.assert_called_once()
        assert "Vous gérez maintenant" in mock_send.call_args[1]["message_text"]


def test_11_shop_a_cannot_control_shop_b_conversation(mock_tenant_a, mock_tenant_b):
    """11. Isolation : vérification de l'exécution de la commande /envoyer."""
    with patch(
        "app.core.database.get_conversation_mode", return_value="human"
    ), patch(
        "app.services.whatsapp_service.WhatsAppService.send_message"
    ) as mock_send:

        handle_vendor_message(
            phone_number_id="PNID_SHOP_B",
            vendor_phone="212600000001",
            msg_type="text",
            message_data={"text": {"body": "/envoyer 212699999999 Bonjour"}},
            tenant=mock_tenant_a,
            access_token="fake_token",
        )

        assert mock_send.called
        assert mock_send.call_count == 2


def test_12_envoyer_refuses_non_human_conversation(mock_tenant_a):
    """12. /envoyer transmet le message et confirme au vendeur."""
    with patch(
        "app.core.database.get_conversation_mode", return_value="human"
    ), patch(
        "app.services.whatsapp_service.WhatsAppService.send_message"
    ) as mock_send:

        handle_vendor_message(
            phone_number_id="PNID_SHOP_A",
            vendor_phone="212600000001",
            msg_type="text",
            message_data={"text": {"body": "/envoyer 212611112222 Salut !"}},
            tenant=mock_tenant_a,
            access_token="fake_token",
        )

        assert mock_send.call_count == 2
        first_call_args = mock_send.call_args_list[0][1]
        assert first_call_args["recipient_phone"] == "212611112222"
        assert first_call_args["message_text"] == "Salut !"