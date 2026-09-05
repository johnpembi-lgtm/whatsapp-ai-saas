from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from app.services.retargeting_service import RetargetingService


def _build_recursive_supabase_mock(data_to_return):
    """
    Crée un mock universel récursif pour les requêtes Supabase.
    N'importe quelle propriété ou méthode (ex: .select, .eq, .not_, .is_) 
    renvoie le mock lui-même, et .execute() renvoie le jeu de données spécifié.
    """
    mock_obj = MagicMock()
    mock_response = MagicMock()
    mock_response.data = data_to_return
    
    mock_obj.execute.return_value = mock_response

    # Gestion de la récursion pour toutes les méthodes de filtrage PostgREST
    mock_obj.select.return_value = mock_obj
    mock_obj.update.return_value = mock_obj
    mock_obj.delete.return_value = mock_obj
    mock_obj.eq.return_value = mock_obj
    mock_obj.in_.return_value = mock_obj
    mock_obj.lte.return_value = mock_obj
    mock_obj.gte.return_value = mock_obj
    mock_obj.is_.return_value = mock_obj
    mock_obj.filter.return_value = mock_obj
    mock_obj.not_ = mock_obj  # support du modificateur .not_

    return mock_obj


def test_expire_stale_carts_after_24h():
    now = datetime.now(timezone.utc)
    mock_chain = _build_recursive_supabase_mock([{"id": 10}, {"id": 11}])

    with patch("app.services.retargeting_service.supabase_db") as mock_db:
        mock_db.table.return_value = mock_chain

        RetargetingService._expire_stale_carts(now)

        # Vérifie qu'un appel d'update a eu lieu sur la chaîne
        assert mock_chain.update.called, "La méthode .update() aurait dû être appelée."


def test_process_reminder_1_trigger(dummy_tenant):
    now = datetime.now(timezone.utc)

    stale_cart = {
        "id": 1,
        "phone_number_id": "100200300",
        "customer_phone": "212699887766",
        "last_product": "T-shirt Noir",
        "reminder_1_sent": False,
        "status": "active"
    }

    mock_chain = _build_recursive_supabase_mock([stale_cart])

    with patch("app.services.retargeting_service.supabase_db") as mock_db, \
         patch("app.core.tenant_manager.TenantManager.get_tenant_by_phone_id", return_value=dummy_tenant), \
         patch("app.services.whatsapp_service.WhatsAppService.send_message", return_value=True) as mock_send:

        mock_db.table.return_value = mock_chain

        RetargetingService._process_reminder_1(now)

        assert mock_send.call_count >= 1, "Le message de relance n'a pas été déclenché."

        args, kwargs = mock_send.call_args
        message_text = kwargs.get("message_text", args[1] if len(args) > 1 else "")
        recipient_phone = kwargs.get("recipient_phone", args[0] if len(args) > 0 else "")

        assert "T-shirt Noir" in message_text
        assert recipient_phone == "212699887766"