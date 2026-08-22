import threading
import logging
from collections import deque
from flask import Blueprint, request, jsonify, current_app

from app.core.tenant_manager import TenantManager
from app.services.message_processor import process as process_message
from app.utils.webhook_security import verify_meta_signature

webhook_bp = Blueprint("webhook", __name__)
logger = logging.getLogger(__name__)

MAX_PROCESSED_MESSAGES = 2000
PROCESSED_MESSAGE_IDS = set()
PROCESSED_QUEUE = deque()
PROCESSED_LOCK = threading.Lock()


def process_message_async(app, tenant, phone_number_id, sender_phone, message_data):
    """Traitement en arrière-plan avec contexte d'application Flask."""
    with app.app_context():
        try:
            process_message(tenant, phone_number_id, sender_phone, message_data)
        except Exception as e:
            logger.error(f"❌ Erreur lors du traitement asynchrone du message : {e}")


@webhook_bp.route("/webhook", methods=["GET"])
def verify_webhook():
    """Validation initiale du Webhook Meta."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == current_app.config.get("WEBHOOK_VERIFY_TOKEN"):
            logger.info("✅ Webhook Meta vérifié avec succès !")
            return challenge, 200
        else:
            logger.warning("❌ Token Webhook invalide.")
            return jsonify({"error": "Token de vérification invalide"}), 403

    return jsonify({"error": "Requête invalide"}), 400


@webhook_bp.route("/webhook", methods=["POST"])
def handle_webhook():
    """Réception des webhooks WhatsApp en temps réel."""
    
    # 1. Sécurité : Vérification de la signature Meta
    secret_key = current_app.config.get("SECRET_KEY")
    if secret_key and not verify_meta_signature(secret_key):
        return jsonify({"status": "error", "message": "Signature invalide ou non autorisée"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Aucune donnée reçue"}), 400

    if data.get("object") == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")
                messages = value.get("messages", [])

                if messages:
                    for message in messages:
                        msg_id = message.get("id")

                        with PROCESSED_LOCK:
                            if msg_id in PROCESSED_MESSAGE_IDS:
                                logger.warning(f"⚠️ Message doublon ignoré : {msg_id}")
                                continue

                            PROCESSED_MESSAGE_IDS.add(msg_id)
                            PROCESSED_QUEUE.append(msg_id)

                            if len(PROCESSED_QUEUE) > MAX_PROCESSED_MESSAGES:
                                oldest_id = PROCESSED_QUEUE.popleft()
                                PROCESSED_MESSAGE_IDS.remove(oldest_id)

                        sender_phone = message.get("from")
                        tenant = TenantManager.get_tenant_by_phone_id(phone_number_id)

                        if tenant:
                            app = current_app._get_current_object()
                            threading.Thread(
                                target=process_message_async,
                                args=(app, tenant, phone_number_id, sender_phone, message),
                            ).start()

        return jsonify({"status": "success"}), 200

    return jsonify({"status": "not_a_whatsapp_event"}), 404