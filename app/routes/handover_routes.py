import logging
from flask import Blueprint, jsonify, request, session
import app.services.handover_service as HandoverService
from app.core import database

logger = logging.getLogger(__name__)

handover_bp = Blueprint("handover", __name__, url_prefix="/api/handover")


@handover_bp.route("/status", methods=["GET"])
def get_handover_status():
    """
    Récupère le mode actuel (bot/human) d'une conversation client.
    Accès strictement limité au tenant de la session.
    """
    # 1. Authentification session
    session_tenant_id = session.get("tenant_id")
    if not session_tenant_id:
        return jsonify({"error": "Non authentifié"}), 401

    customer_phone = request.args.get("customer_phone")
    if not customer_phone:
        return jsonify({"error": "Paramètre customer_phone requis."}), 400

    # 2. Récupération du phone_number_id prioritairement depuis la session
    phone_number_id = session.get("phone_number_id") or request.args.get("phone_number_id")
    if not phone_number_id:
        return jsonify({"error": "phone_number_id introuvable"}), 400

    # 3. Vérification de l'appartenance du client au tenant authentifié (Test 18)
    try:
        customer_query = (
            database.supabase_db
            .table("customers")
            .select("id, tenant_id")
            .eq("phone", customer_phone)
            .maybe_single()
            .execute()
        )
        customer_data = customer_query.data if customer_query else None
    except Exception as e:
        logger.warning(f"Impossible de vérifier le client via Supabase: {e}")
        customer_data = None

    # Si le client appartient à un autre tenant -> 403 Forbidden
    if customer_data:
        owner_tenant_id = customer_data.get("tenant_id")
        if owner_tenant_id and str(owner_tenant_id) != str(session_tenant_id):
            return jsonify({"error": "Accès interdit à cette conversation."}), 403

    # 4. Fallback/Contrôle direct via HandoverService
    mode = HandoverService.get_mode(phone_number_id, customer_phone)
    if mode is None or not customer_data:
        return jsonify({"error": "Conversation introuvable."}), 404

    return jsonify({
        "status": "success",
        "customer_phone": customer_phone,
        "phone_number_id": phone_number_id,
        "mode": mode,
        "handover_active": (mode == "human")
    }), 200


@handover_bp.route("/toggle", methods=["POST"])
def toggle_handover_mode():
    """Bascule le mode de conversation entre 'bot' et 'human'."""
    tenant_id = session.get("tenant_id")
    if not tenant_id:
        return jsonify({"error": "Non authentifié"}), 401

    data = request.get_json() or {}
    phone_number_id = data.get("phone_number_id") or session.get("phone_number_id")
    customer_phone = data.get("customer_phone")

    target_mode = data.get("mode")
    handover_active = data.get("handover_active")

    if target_mode is None and handover_active is not None:
        target_mode = "human" if handover_active else "bot"

    if not phone_number_id or not customer_phone or target_mode not in ("bot", "human"):
        return jsonify({"error": "Champs invalides ou manquants."}), 400

    tenant_data = session.get("tenant") or {"id": tenant_id}

    if target_mode == "human":
        access_token = data.get("access_token", "")
        success = HandoverService.activate_human_mode(
            phone_number_id=phone_number_id,
            customer_phone=customer_phone,
            tenant=tenant_data,
            access_token=access_token,
            trigger_message="Changement manuel via API"
        )
    else:
        success = HandoverService.deactivate_human_mode(
            phone_number_id=phone_number_id,
            customer_phone=customer_phone
        )

    if not success:
        return jsonify({"error": "Action non autorisée ou échec de mise à jour."}), 403

    logger.info(f"🔄 Mode basculé vers '{target_mode}' pour +{customer_phone} (Tenant: {tenant_id})")

    return jsonify({
        "status": "success",
        "customer_phone": customer_phone,
        "new_mode": target_mode,
        "handover_active": (target_mode == "human")
    }), 200


@handover_bp.route("/active-human", methods=["GET"])
def list_active_human_conversations():
    """Liste toutes les conversations gérées par un agent humain pour ce tenant."""
    tenant_id = session.get("tenant_id")
    if not tenant_id:
        return jsonify({"error": "Non authentifié"}), 401

    phone_number_id = session.get("phone_number_id") or request.args.get("phone_number_id")
    if not phone_number_id:
        return jsonify({"error": "Paramètre phone_number_id requis."}), 400

    conversations = HandoverService.get_active_human_conversations(
        phone_number_id=phone_number_id
    )

    return jsonify({
        "status": "success",
        "count": len(conversations),
        "conversations": conversations
    }), 200