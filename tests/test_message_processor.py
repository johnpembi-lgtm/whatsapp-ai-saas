from unittest.mock import patch
from app.services.message_processor import process

def test_process_vendor_routing(dummy_tenant):
    vendor_phone = "212600000000"
    message_data = {"type": "text", "text": {"body": "Desactiver bot"}}

    with patch("app.services.message_processor.handle_vendor_message") as mock_vendor, \
         patch("app.services.message_processor.handle_customer_message") as mock_customer:

        process(dummy_tenant, "100200300", vendor_phone, message_data)

        # Le flux doit aller EXCLUSIVEMENT au vendeur
        mock_vendor.assert_called_once()
        mock_customer.assert_not_called()

def test_process_customer_routing(dummy_tenant):
    customer_phone = "212611112222"  # Numéro différent du vendeur
    message_data = {"type": "text", "text": {"body": "Quel est le prix ?"}}

    with patch("app.services.message_processor.handle_vendor_message") as mock_vendor, \
         patch("app.services.message_processor.handle_customer_message") as mock_customer:

        process(dummy_tenant, "100200300", customer_phone, message_data)

        # Le flux doit aller EXCLUSIVEMENT au client
        mock_customer.assert_called_once()
        mock_vendor.assert_not_called()