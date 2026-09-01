import os
import functools
import hmac
import secrets
import logging
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    Response,
    current_app,
    session,
    abort,
)
from app.core.tenant_manager import TenantManager
from app.core import database
from app.services.sheets_service import SheetsService
from app.services.orders_service import OrdersService

admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        expected_user = current_app.config.get("ADMIN_USERNAME", "admin")
        expected_pass = current_app.config.get("ADMIN_PASSWORD")

        if (
            not expected_pass
            or not auth
            or auth.username != expected_user
            or auth.password != expected_pass
        ):
            return Response(
                "Accès refusé. Veuillez fournir des identifiants valides.",
                401,
                {"WWW-Authenticate": 'Basic realm="Accès Administration"'},
            )
        return f(*args, **kwargs)

    return decorated


@admin_bp.route("/admin", methods=["GET"])
@admin_required
def dashboard():
    tenants = TenantManager.get_tenants()
    csrf_token = session.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["csrf_token"] = csrf_token
    return render_template("admin.html", tenants=tenants, csrf_token=csrf_token)


@admin_bp.route("/admin/add-tenant", methods=["POST"])
@admin_required
def add_tenant():
    expected_csrf = session.get("csrf_token", "")
    received_csrf = request.form.get("csrf_token", "")
    if not expected_csrf or not hmac.compare_digest(expected_csrf, received_csrf):
        abort(400, description="Jeton CSRF invalide.")

    store_id = request.form.get("store_id")
    phone_number_id = request.form.get("phone_number_id")
    vendor_phone = request.form.get("vendor_phone")
    vendor_email = request.form.get("vendor_email", "").strip()
    sheets_id = request.form.get("sheets_id", "").strip()
    system_prompt = request.form.get("system_prompt", "")

    if not phone_number_id or not vendor_phone or not store_id:
        flash(
            "Les champs Store ID, Phone Number ID et Numéro Vendeur sont obligatoires.",
            "error",
        )
        return redirect(url_for("admin.dashboard"))

    # 1. TENTATIVE DE CRÉATION DU GOOGLE SHEET (Optionnelle / Non-bloquante)
    if not sheets_id:
        try:
            sheets_id = SheetsService.create_store_sheet(
                store_id, vendor_email=vendor_email
            )
            if sheets_id:
                flash(
                    f"✅ Google Sheet créé automatiquement avec succès pour '{store_id}'.",
                    "success",
                )
            else:
                flash(
                    "⚠️ La création automatique du Google Sheet a échoué. "
                    "La boutique a tout de même été créée sur Supabase. "
                    "Vous pourrez associer un ID Google Sheet ultérieurement.",
                    "warning",
                )
        except Exception as e:
            logger.warning(
                f"⚠️ Erreur non-bloquante lors de la création Google Sheets : {e}"
            )
            flash(
                "⚠️ Erreur lors de la configuration Google Sheets (OAuth2/Drive). La boutique est active sans Sheet.",
                "warning",
            )
            sheets_id = None

    # 2. ENREGISTREMENT EN BASE DE DONNÉES SUPABASE (Prioritaire)
    success = TenantManager.add_or_update_tenant(
        phone_number_id=phone_number_id,
        store_id=store_id,
        vendor_phone=vendor_phone,
        sheets_id=sheets_id,
        system_prompt=system_prompt,
        vendor_email=vendor_email,
    )

    if success:
        flash(f"Boutique '{store_id}' enregistrée avec succès !", "success")
    else:
        flash("Une erreur est survenue lors de l'enregistrement dans la base de données.", "error")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/admin/store/<phone_number_id>", methods=["GET"])
@admin_required
def store_dashboard(phone_number_id):
    """Dashboard V1 d'une boutique précise : commandes, stock, conversations,
    statistiques. Vue opérationnelle, distincte du panneau de configuration
    multi-tenant."""
    tenant = TenantManager.get_tenant_by_phone_id(phone_number_id)
    if not tenant:
        flash("Boutique introuvable.", "error")
        return redirect(url_for("admin.dashboard"))

    catalog = SheetsService.fetch_catalog(tenant.get("sheets_id"))
    recent_orders = OrdersService.get_recent_orders(tenant, limit=20)
    today_stats = OrdersService.get_today_stats(tenant)
    cart_funnel = database.get_cart_funnel_stats(phone_number_id)
    conversations = database.get_recent_conversations(phone_number_id, limit=20)

    return render_template(
        "store_dashboard.html",
        tenant=tenant,
        phone_number_id=phone_number_id,
        catalog=catalog,
        recent_orders=recent_orders,
        today_stats=today_stats,
        cart_funnel=cart_funnel,
        conversations=conversations,
    )