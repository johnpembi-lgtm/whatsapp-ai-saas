import sys
from pathlib import Path

# Ajoute la racine du projet (whatsapp-ai-saas) dans le PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from unittest.mock import MagicMock, patch
from app import create_app


@pytest.fixture
def app():
    """Crée une instance de l'application Flask configurée pour les tests."""
    _app = create_app()
    _app.config.update({
        "TESTING": True,
        "DEBUG": False
    })
    yield _app


@pytest.fixture
def client(app):
    """Client HTTP pour exécuter les requêtes dans les tests."""
    return app.test_client()


@pytest.fixture
def dummy_tenant():
    return {
        "id": "tenant-uuid-123",
        "tenant_id": "tenant-uuid-123",
        "phone_number_id": "100200300",
        "store_id": "BoutiqueTest",
        "store_name": "Boutique Test",
        "vendor_phone": "212600000000",
        "sheets_id": "sheets_id_abc123",
        "system_prompt": "Tu es un assistant virtuel.",
        "is_active": True,
        "whatsapp_access_token": "fake_wa_token"
    }


@pytest.fixture
def mock_supabase_db():
    mock_db = MagicMock()
    with patch("app.core.database.supabase_db", mock_db):
        yield mock_db


@pytest.fixture
def authenticated_client_tenant_a(client, dummy_tenant):
    """
    Client HTTP simulé avec une session authentifiée pour le Tenant A.
    Injection du tenant_id en session Flask et via les headers de requête.
    """
    with client.session_transaction() as sess:
        sess["tenant_id"] = dummy_tenant["tenant_id"]
        sess["user_id"] = "user-tenant-a-123"
        sess["role"] = "admin"

    # Permet de couvrir aussi les routes lisant le tenant depuis les headers HTTP
    client.environ_base["HTTP_X_TENANT_ID"] = dummy_tenant["tenant_id"]
    client.environ_base["HTTP_AUTHORIZATION"] = "Bearer fake_auth_token_tenant_a"
    
    return client