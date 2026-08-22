"""
Test manuel du flux de relance (paniers abandonnés).

Simule un panier "pending" vieux de 3h pour un tenant réel existant dans
Supabase, puis déclenche manuellement RetargetingService.process_abandoned_carts()
pour vérifier que la relance se comporte comme prévu.

Usage : python test_flow.py
"""
from datetime import datetime, timedelta, timezone

from app import create_app
from app.core import database
from app.core.tenant_manager import TenantManager
from app.services.retargeting_service import RetargetingService


def get_test_tenant():
    """Récupère le premier tenant actif trouvé dans Supabase, pour ne pas
    dépendre d'un phone_number_id codé en dur qui pourrait ne plus exister."""
    tenants = TenantManager.get_tenants()
    for phone_number_id, tenant in tenants.items():
        if tenant.get("is_active", True):
            return phone_number_id, tenant
    return None, None


def simulate_abandoned_cart(phone_number_id, customer_phone, product_name):
    """Injecte directement un panier 'pending' avec une date d'interaction
    simulée il y a 3h (pour tomber dans la fenêtre de relance 2h-22h).

    On utilise le client Supabase directement (pas update_cart_tracking)
    car cette fonction force toujours last_interaction à 'now()'."""
    if not database.supabase_db:
        print("❌ Client Supabase non initialisé — vérifie ton .env (SUPABASE_URL / SUPABASE_KEY)")
        return False

    fake_interaction_time = (
        datetime.now(timezone.utc) - timedelta(hours=3)
    ).isoformat()

    payload = {
        "phone_number_id": str(phone_number_id),
        "customer_phone": str(customer_phone),
        "last_product": product_name,
        "last_interaction": fake_interaction_time,
        "status": "pending",
    }

    try:
        database.supabase_db.table("cart_tracking").upsert(
            payload, on_conflict="phone_number_id,customer_phone"
        ).execute()
        print(f"📥 Panier fictif injecté avec succès (date simulée : {fake_interaction_time})")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de l'injection du panier : {e}")
        return False


if __name__ == "__main__":
    app = create_app()

    with app.app_context():
        print("🧪 [TEST] Début de la simulation du flux de relance...\n")

        phone_number_id, tenant = get_test_tenant()
        if not phone_number_id:
            print("❌ Aucun tenant actif trouvé dans Supabase. Ajoute d'abord une boutique via TenantManager.add_or_update_tenant().")
            raise SystemExit(1)

        print(f"🏪 Tenant utilisé pour le test : {tenant.get('store_name')} ({phone_number_id})")

        # Remplace par ton propre numéro pour recevoir un vrai message WhatsApp de relance
        test_customer_phone = "22990000000"
        test_product = "Montre Connectée Sport"

        success = simulate_abandoned_cart(phone_number_id, test_customer_phone, test_product)
        if not success:
            raise SystemExit(1)

        print("\n⚡ [TEST] Déclenchement manuel du traitement des paniers abandonnés...")
        RetargetingService.process_abandoned_carts()