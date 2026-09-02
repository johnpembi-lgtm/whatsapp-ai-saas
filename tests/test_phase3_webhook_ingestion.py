import pytest
import uuid
from unittest.mock import patch
from app import create_app

# 1. Instanciation unique de l'application Flask pour toute la session de test
@pytest.fixture(scope="session")
def app_instance():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WEBHOOK_VERIFY_TOKEN"] = "test_verify_token"
    app.config["APP_SECRET"] = "test_app_secret"
    return app

# 2. Fixture fournissant le client de test Flask
@pytest.fixture
def webhook_client(app_instance):
    return app_instance.test_client()


# --- TESTS VERIFY WEBHOOK (GET) ---

def test_verify_webhook_success(webhook_client):
    """Valide la poignée de main GET avec un token correct."""
    response = webhook_client.get(
        "/webhook?hub.mode=subscribe&hub.verify_token=test_verify_token&hub.challenge=123456"
    )
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "123456"


def test_verify_webhook_invalid_token(webhook_client):
    """Vérifie le rejet HTTP 403 si le token est invalide."""
    response = webhook_client.get(
        "/webhook?hub.mode=subscribe&hub.verify_token=WRONG_TOKEN&hub.challenge=123456"
    )
    assert response.status_code == 403


# --- TESTS INGESTION WEBHOOK (POST) ---

@patch("app.routes.webhook_routes.verify_meta_signature", return_value=True)
@patch("app.routes.webhook_routes.TenantManager.get_tenant_by_phone_id")
@patch("app.routes.webhook_routes.PersistentDeduplicator.register_and_check")
@patch("app.routes.webhook_routes.MESSAGE_EXECUTOR.submit")
def test_post_webhook_success_and_idempotency(
    mock_executor, mock_dedup, mock_get_tenant, mock_verify_sig, webhook_client
):
    """Vérifie l'ingestion d'un message puis son rejet immédiat s'il est dupliqué."""
    msg_id = f"wam_test_{uuid.uuid4().hex}"
    
    mock_get_tenant.return_value = {"id": "tenant_123", "tenant_id": "tenant_123"}
    
    # Premier appel -> Pas un doublon (is_duplicate = False)
    mock_dedup.return_value = (False, "registered")

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "wa_phone_999"},
                    "messages": [{
                        "id": msg_id,
                        "from": "212600000000",
                        "type": "text",
                        "text": {"body": "Bonjour PEMBI"}
                    }]
                }
            }]
        }]
    }

    # 1. Premier envoi
    res1 = webhook_client.post("/webhook", json=payload)
    assert res1.status_code == 200
    assert res1.get_json() == {"status": "success"}
    assert mock_executor.call_count == 1

    # Deuxième appel avec le même message -> Doublon détecté (is_duplicate = True)
    mock_dedup.return_value = (True, "already_processed")

    # 2. Ré-émission (Doublon)
    res2 = webhook_client.post("/webhook", json=payload)
    assert res2.status_code == 200
    assert res2.get_json() == {"status": "success"}
    
    # L'exécuteur ne doit pas avoir été appelé une seconde fois
    assert mock_executor.call_count == 1