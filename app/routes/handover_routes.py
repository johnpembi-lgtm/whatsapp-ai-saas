import logging
from flask import Blueprint, jsonify, request
import app.services.handover_service as HandoverService

logger = logging.getLogger(__name__)

# La variable s'appelle bien handover_bp pour app/__init__.py
handover_bp = Blueprint("handover", __name__, url_prefix="/api/handover")


@handover_bp.route("/status", methods=["GET"])
def get_handover_status():
    """Récupère le mode actuel (bot/human) d'une conversation client."""
    phone_number_id = request.args.get("phone_number_id")
    customer_phone = request.args.get("customer_phone")

    if not phone_number_id or not customer_phone:
        return jsonify({"error": "Paramètres phone_number_id et customer_phone requis."}), 400

    mode = HandoverService.get_mode(phone_number_id, customer_phone)
    return jsonify({
        "status": "success",
        "phone_number_id": phone_number_id,
        "customer_phone": customer_phone,
        "mode": mode
    }), 200


@handover_bp.route("/toggle", methods=["POST"])
def toggle_handover_mode():
    """Bascule le mode de conversation entre 'bot' et 'human'."""
    data = request.get_json() or {}
    phone_number_id = data.get("phone_number_id")
    customer_phone = data.get("customer_phone")
    target_mode = data.get("mode")  # 'bot' ou 'human'

    if not phone_number_id or not customer_phone or target_mode not in ("bot", "human"):
        return jsonify({"error": "Champs phone_number_id, customer_phone et mode ('bot'|'human') requis."}), 400

    if target_mode == "human":
        # Activer le mode humain (notification vendeur facultative ou à charger depuis le tenant)
        tenant = data.get("tenant", {})
        access_token = data.get("access_token", "")
        success = HandoverService.activate_human_mode(
            phone_number_id=phone_number_id,
            customer_phone=customer_phone,
            tenant=tenant,
            access_token=access_token,
            trigger_message="Changement manuel via API"
        )
    else:
        # Désactiver et rendre la main au bot
        success = HandoverService.deactivate_human_mode(phone_number_id, customer_phone)

    if not success:
        return jsonify({"error": "Échec de la mise à jour du mode."}), 500

    logger.info(f"🔄 Mode basculé vers '{target_mode}' pour +{customer_phone}")
    return jsonify({
        "status": "success",
        "customer_phone": customer_phone,
        "new_mode": target_mode
    }), 200


@handover_bp.route("/active-human", methods=["GET"])
def list_active_human_conversations():
    """Liste toutes les conversations actuellement gérées par un agent humain."""
    phone_number_id = request.args.get("phone_number_id")
    if not phone_number_id:
        return jsonify({"error": "Paramètre phone_number_id requis."}), 400

    conversations = HandoverService.get_active_human_conversations(phone_number_id)
    return jsonify({
        "status": "success",
        "count": len(conversations),
        "conversations": conversations
    }), 200