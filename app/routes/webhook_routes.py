import logging
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, jsonify, current_app

from app.core.tenant_manager import TenantManager
from app.services.message_processor import process as process_message
from app.utils.webhook_security import verify_meta_signature
from app.utils.deduplicator import PersistentDeduplicator

webhook_bp = Blueprint("webhook", __name__)
logger = logging.getLogger(__name__)

# Executor pour le traitement asynchrone sans bloquer la réponse Webhook 200 OK de Meta
MESSAGE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pemby-webhook")


def process_message_async(app, tenant, phone_number_id, sender_phone, message_data, msg_id):
    """Exécute le traitement du message dans un thread séparé avec le contexte Flask."""
    with app.app_context():
        try:
            process_message(tenant, phone_number_id, sender_phone, message_data)
            # Validation définitive de la déduplication après succès
            PersistentDeduplicator.mark_processed(msg_id)
        except Exception as e:
            logger.error(f"💥 Erreur lors du traitement asynchrone du message {msg_id} : {e}")
            # Enregistrement de l'échec pour audit
            PersistentDeduplicator.mark_failed(msg_id, str(e))


@webhook_bp.route("/webhook", methods=["GET"])
def verify_webhook():
    """Validation initiale du Webhook Meta (GET)."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    verify_token = current_app.config.get("WEBHOOK_VERIFY_TOKEN")

    if mode and token:
        if mode == "subscribe" and token == verify_token:
            logger.info("✅ Webhook Meta vérifié avec succès !")
            return challenge, 200
        else:
            logger.warning("❌ Token Webhook invalide.")
            return jsonify({"error": "Token de vérification invalide"}), 403

    return jsonify({"error": "Requête invalide"}), 400


@webhook_bp.route("/webhook", methods=["POST"])
def handle_webhook():
    """Réception et déduplication persistante des webhooks WhatsApp (POST)."""
    
    # 1. Sécurité : Vérification de la signature HMAC Meta
    app_secret = current_app.config.get("APP_SECRET")
    if not app_secret:
        logger.error("APP_SECRET absent : webhook refusé.")
        return jsonify({"status": "error", "message": "Configuration webhook incomplète"}), 503
        
    if not verify_meta_signature(app_secret):
        logger.error("⛔ Signature Meta invalide.")
        return jsonify({"status": "error", "message": "Signature invalide ou non autorisée"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Aucune donnée reçue"}), 400

    if data.get("object") == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")

                if not phone_number_id:
                    continue

                # 2. Identification du Tenant
                tenant = TenantManager.get_tenant_by_phone_id(phone_number_id)
                if not tenant:
                    logger.warning(f"⚠️ Aucun tenant trouvé ou actif pour phone_number_id: {phone_number_id}")
                    continue

                tenant_id = tenant.get("tenant_id") or tenant.get("id")

                # 3. Traitement des statuts de délivrabilité Meta (sent, delivered, read)
                statuses = value.get("statuses", [])
                if statuses:
                    for status_item in statuses:
                        status_type = status_item.get("status")
                        recipient = status_item.get("recipient_id")
                        logger.info(f"ℹ️ Statut message Meta : [{status_type}] pour {recipient}")
                        if "errors" in status_item:
                            logger.error(f"❌ Erreur Meta reçue : {status_item.get('errors')}")
                    continue

                # 4. Traitement des messages entrants
                messages = value.get("messages", [])
                if not messages:
                    continue

                for message in messages:
                    msg_id = message.get("id")
                    msg_type = message.get("type", "unknown")

                    if not msg_id:
                        continue

                    # 5. Contrôle de Déduplication Persistante en base de données
                    is_duplicate, status = PersistentDeduplicator.register_and_check(
                        message_id=msg_id,
                        tenant_id=tenant_id,
                        event_type=f"message_{msg_type}"
                    )

                    if is_duplicate:
                        logger.info(f"⏭️ Message doublon ignoré : {msg_id} (Statut: {status})")
                        continue

                    sender_phone = message.get("from")
                    app = current_app._get_current_object()

                    # 6. Lancement du traitement asynchrone
                    MESSAGE_EXECUTOR.submit(
                        process_message_async, app, tenant, phone_number_id, sender_phone, message, msg_id
                    )

        return jsonify({"status": "success"}), 200

    return jsonify({"status": "not_a_whatsapp_event"}), 404