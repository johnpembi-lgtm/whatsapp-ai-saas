"""
Test manuel du Human Handover (Phase 2), couvrant les 8 scénarios de la
doc d'architecture. Ne fait pas d'assertions automatiques (pas de vrai
message WhatsApp envoyé ici) — affiche l'état à chaque étape pour
vérification visuelle. À lancer avec : python test_handover.py
"""
from app import create_app
from app.core.tenant_manager import TenantManager
from app.services import handover_service


def get_test_tenant():
    tenants = TenantManager.get_tenants()
    for phone_number_id, tenant in tenants.items():
        if tenant.get("is_active", True):
            return phone_number_id, tenant
    return None, None


if __name__ == "__main__":
    app = create_app()

    with app.app_context():
        phone_number_id, tenant = get_test_tenant()
        if not phone_number_id:
            print("❌ Aucun tenant actif trouvé dans Supabase.")
            raise SystemExit(1)

        test_customer_a = "22990000001"
        test_customer_b = "22990000002"

        print(f"🏪 Tenant utilisé : {tenant.get('store_name')} ({phone_number_id})\n")

        # --- Test 2 : Client A demande un humain → HUMAN_MODE ---
        print("🧪 Test 2 — Transfert déclenché par mot-clé")
        triggered = handover_service.is_transfer_requested("Je veux parler au responsable")
        print(f"   is_transfer_requested(...) = {triggered} (attendu: True)")

        # --- Test 8 : Client A en HUMAN_MODE, Client B en BOT_MODE, indépendamment ---
        print("\n🧪 Test 8 — Isolation multi-client")
        handover_service.activate_human_mode(
            phone_number_id, test_customer_a, tenant, access_token=None,
            trigger_message="(test manuel)",
        )
        mode_a = handover_service.get_mode(phone_number_id, test_customer_a)
        mode_b = handover_service.get_mode(phone_number_id, test_customer_b)
        print(f"   Client A ({test_customer_a}) → mode = {mode_a} (attendu: human)")
        print(f"   Client B ({test_customer_b}) → mode = {mode_b} (attendu: bot)")

        assert mode_a == "human", "❌ ÉCHEC : Client A devrait être en human"
        assert mode_b == "bot", "❌ ÉCHEC : Client B devrait rester en bot (isolation cassée !)"
        print("   ✅ Isolation confirmée : A et B sont bien indépendants.")

        # --- Test 6 : /reprendre → retour en BOT_MODE ---
        print("\n🧪 Test 6 — /reprendre (retour à l'IA)")
        handover_service.deactivate_human_mode(phone_number_id, test_customer_a)
        mode_a_after = handover_service.get_mode(phone_number_id, test_customer_a)
        print(f"   Client A après /reprendre → mode = {mode_a_after} (attendu: bot)")
        assert mode_a_after == "bot", "❌ ÉCHEC : le retour en bot n'a pas fonctionné"
        print("   ✅ Retour en BOT_MODE confirmé.")

        print("\n✅ Tous les tests handover sont passés avec succès.")
        print("\nℹ️  Pour les tests 1, 3, 4, 5, 7 (bout-en-bout avec vrais messages),")
        print("   il faut tester manuellement via WhatsApp réel — voir la checklist")
        print("   dans le document d'architecture Phase 2 (section 15).")