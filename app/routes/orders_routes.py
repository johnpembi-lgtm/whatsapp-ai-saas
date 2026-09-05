"""
Routes API pour la gestion des commandes depuis le Dashboard Vendeur.
Permet la consultation, le filtrage et le passage de statut (avec MAJ de stock atomique).
"""
import logging
from flask import Blueprint, jsonify, request, session
from app.core import database

orders_bp = Blueprint("orders_bp", __name__, url_prefix="/api/orders")
logger = logging.getLogger(__name__)


@orders_bp.route("", methods=["GET"])
def list_orders():
    """Liste les commandes du tenant de la session courante."""
    phone_number_id = session.get("phone_number_id")
    if not phone_number_id:
        return jsonify({"error": "Non autorisé / Session expirée"}), 401

    tenant_id = database._get_tenant_id(phone_number_id)
    if not tenant_id:
        return jsonify({"error": "Tenant introuvable"}), 404

    status_filter = request.args.get("status")
    limit = int(request.args.get("limit", 50))

    orders = database.get_orders_by_tenant(tenant_id, status=status_filter, limit=limit)
    return jsonify({"success": True, "orders": orders}), 200


@orders_bp.route("/<order_id>/status", methods=["PATCH"])
def update_order_status(order_id):
    """Met à jour le statut d'une commande du tenant courant."""

    phone_number_id = session.get("phone_number_id")

    if not phone_number_id:
        return jsonify({"error": "Non autorisé"}), 401

    tenant_id = database._get_tenant_id(phone_number_id)

    if not tenant_id:
        return jsonify({"error": "Tenant introuvable"}), 404

    data = request.get_json() or {}
    new_status = data.get("status")

    valid_statuses = [
        "pending",
        "processing",
        "completed",
        "cancelled",
    ]

    if not new_status or new_status not in valid_statuses:
        return jsonify({
            "error": f"Statut invalide. Statuts autorisés : {valid_statuses}"
        }), 400

    res = database.update_order_status_atomic(
        order_id,
        new_status,
        tenant_id=tenant_id,
    )

    if res.get("success"):
        return jsonify({
            "success": True,
            "message": res.get("message"),
        }), 200

    return jsonify({
        "error": res.get("message")
    }), 400