from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.core.tenant_manager import TenantManager

admin_bp = Blueprint("admin", __name__, template_folder="../templates")


@admin_bp.route("/admin", methods=["GET"])
def dashboard():
    tenants = TenantManager.get_tenants()
    return render_template("admin.html", tenants=tenants)


@admin_bp.route("/admin/add-tenant", methods=["POST"])
def add_tenant():
    store_id = request.form.get("store_id")
    phone_number_id = request.form.get("phone_number_id")
    vendor_phone = request.form.get("vendor_phone")
    sheets_id = request.form.get("sheets_id")
    system_prompt = request.form.get("system_prompt")

    if not phone_number_id or not vendor_phone or not sheets_id:
        flash("Tous les champs obligatoires doivent être remplis.", "error")
        return redirect(url_for("admin.dashboard"))

    success = TenantManager.add_or_update_tenant(
        phone_number_id=phone_number_id,
        store_id=store_id or phone_number_id,
        vendor_phone=vendor_phone,
        sheets_id=sheets_id,
        system_prompt=system_prompt,
    )

    if success:
        flash(f"Boutique '{store_id}' enregistrée avec succès en base de données !", "success")
    else:
        flash("Une erreur est survenue lors de l'enregistrement.", "error")

    return redirect(url_for("admin.dashboard"))