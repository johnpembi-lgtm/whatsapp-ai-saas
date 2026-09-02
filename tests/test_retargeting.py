from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from app.services.retargeting_service import RetargetingService

def test_expire_stale_carts_after_24h(mock_supabase_db):
    now = datetime.now(timezone.utc)

    # Simulation de paniers de +24h retournés par Supabase
    mock_response = MagicMock()
    mock_response.data = [{"id": 10}, {"id": 11}]
    mock_supabase_db.table().select().in_().lte().execute.return_value = mock_response

    RetargetingService._expire_stale_carts(now)

    # Doit mettre à jour les paniers avec le statut "expired"
    mock_supabase_db.table().update.assert_called_with({"status": "expired"})

def test_process_reminder_1_trigger(mock_supabase_db, dummy_tenant):
    now = datetime.now(timezone.utc)

    mock_response = MagicMock()
    mock_response.data = [{
        "id": 1,
        "phone_number_id": "100200300",
        "customer_phone": "212699887766",
        "last_product": "T-shirt Noir"
    }]
    mock_supabase_db.table().select().eq().gte().lte().execute.return_value = mock_response

    with patch("app.core.tenant_manager.TenantManager.get_tenant_by_phone_id", return_value=dummy_tenant), \
         patch("app.services.whatsapp_service.WhatsAppService.send_message", return_value=True) as mock_send:

        RetargetingService._process_reminder_1(now)

        # Vérifie que le message WhatsApp personnalisé est envoyé
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert "T-shirt Noir" in kwargs["message_text"]
        assert kwargs["recipient_phone"] == "212699887766"