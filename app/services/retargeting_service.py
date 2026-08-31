import os
from datetime import datetime, timedelta, timezone
from app.core.database import supabase_db
from app.core.tenant_manager import TenantManager
from app.services.whatsapp_service import WhatsAppService

# ==============================================================================
# STRATÉGIE COST-OPTIMIZED WHATSAPP (FENÊTRE DE 24h STRICTE)
# ==============================================================================
# - Relance 1 : entre 2h et 4h après la dernière interaction client.
# - Relance 2 : entre 18h et 22h après la dernière interaction client (avant expiration 24h).
# - Expiration : à 24h pile, on clôture le panier pour bloquer tout envoi payant hors-session.
# ==============================================================================

REMINDER_1_MIN_HOURS = 2
REMINDER_1_MAX_HOURS = 4

REMINDER_2_MIN_HOURS = 18
REMINDER_2_MAX_HOURS = 22

EXPIRE_AFTER_HOURS = 24  # Fin de la fenêtre gratuite de 24h Meta


class RetargetingService:

    @staticmethod
    def _get_access_token(tenant):
        return (
            tenant.get("whatsapp_access_token")
            or os.getenv("WHATSAPP_ACCESS_TOKEN")
        )

    @staticmethod
    def _send_and_advance(cart, tenant, message, next_status, next_reminder_count):
        access_token = RetargetingService._get_access_token(tenant)

        res_wa = WhatsAppService.send_message(
            phone_number_id=cart["phone_number_id"],
            recipient_phone=cart["customer_phone"],
            message_text=message,
            access_token=access_token,
        )

        if res_wa:
            supabase_db.table("cart_tracking").update({
                "status": next_status,
                "reminder_count": next_reminder_count,
                "last_reminder_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", cart["id"]).execute()
            return True

        print(f"⚠️ Échec d'envoi de relance pour +{cart['customer_phone']} — réessai au prochain scan.")
        return False

    @staticmethod
    def _process_reminder_1(now):
        """pending → reminder_1_sent (entre 2h et 4h)."""
        min_time = (now - timedelta(hours=REMINDER_1_MAX_HOURS)).isoformat()
        max_time = (now - timedelta(hours=REMINDER_1_MIN_HOURS)).isoformat()

        res = supabase_db.table("cart_tracking") \
            .select("id, phone_number_id, customer_phone, last_product") \
            .eq("status", "pending") \
            .gte("last_interaction", min_time) \
            .lte("last_interaction", max_time) \
            .execute()

        carts = res.data or []
        print(f"⏰ [Relance 1 - Gratuit 24h] {len(carts)} panier(s) éligible(s).")

        for cart in carts:
            # Récupération ultra-rapide en mémoire sans ré-interroger Supabase (N+1 évité)
            tenant = TenantManager.get_tenant_by_phone_id(cart["phone_number_id"])
            if not tenant:
                continue

            store_name = tenant.get("store_name", tenant.get("store_id", "notre boutique"))
            last_product = cart.get("last_product")

            if last_product:
                message = (
                    f"Bonjour ! 👋 Avez-vous eu le temps de réfléchir concernant "
                    f"*{last_product}* chez *{store_name}* ? Je reste à votre disposition !"
                )
            else:
                message = (
                    f"Bonjour ! 👋 Je reste disponible si vous avez besoin d'informations "
                    f"complémentaires sur nos articles chez *{store_name}*."
                )

            if RetargetingService._send_and_advance(cart, tenant, message, "reminder_1_sent", 1):
                print(f"🚀 Relance 1 envoyée à +{cart['customer_phone']} ({store_name})")

    @staticmethod
    def _process_reminder_2(now):
        """reminder_1_sent → reminder_2_sent (entre 18h et 22h depuis le début de la conversation)."""
        min_time = (now - timedelta(hours=REMINDER_2_MAX_HOURS)).isoformat()
        max_time = (now - timedelta(hours=REMINDER_2_MIN_HOURS)).isoformat()

        res = supabase_db.table("cart_tracking") \
            .select("id, phone_number_id, customer_phone, last_product") \
            .eq("status", "reminder_1_sent") \
            .gte("last_interaction", min_time) \
            .lte("last_interaction", max_time) \
            .execute()

        carts = res.data or []
        print(f"⏰ [Relance 2 - Ultime relance < 24h] {len(carts)} panier(s) éligible(s).")

        for cart in carts:
            # Récupération ultra-rapide en mémoire sans ré-interroger Supabase (N+1 évité)
            tenant = TenantManager.get_tenant_by_phone_id(cart["phone_number_id"])
            if not tenant:
                continue

            store_name = tenant.get("store_name", tenant.get("store_id", "notre boutique"))
            last_product = cart.get("last_product")

            if last_product:
                message = (
                    f"Dernière petite relance ! 😊 Le produit *{last_product}* vous intéresse "
                    f"toujours ? N'hésitez pas si vous avez des questions chez *{store_name}* !"
                )
            else:
                message = (
                    f"On reste disponible chez *{store_name}* si vous avez besoin de quoi que ce soit ! 😊"
                )

            if RetargetingService._send_and_advance(cart, tenant, message, "reminder_2_sent", 2):
                print(f"🚀 Relance 2 envoyée à +{cart['customer_phone']} ({store_name})")

    @staticmethod
    def _expire_stale_carts(now):
        """Bloque l'envoi de messages si last_interaction > 24h (stoppe les coûts WhatsApp)."""
        cutoff = (now - timedelta(hours=EXPIRE_AFTER_HOURS)).isoformat()

        res = supabase_db.table("cart_tracking") \
            .select("id") \
            .in_("status", ["pending", "reminder_1_sent", "reminder_2_sent"]) \
            .lte("last_interaction", cutoff) \
            .execute()

        carts = res.data or []
        if not carts:
            return

        ids = [c["id"] for c in carts]
        supabase_db.table("cart_tracking").update({"status": "expired"}).in_("id", ids).execute()
        print(f"🛑 {len(carts)} panier(s) expirés (+24h dépassées). Relances stoppées pour éviter les frais WhatsApp.")

    @staticmethod
    def process_abandoned_carts():
        if not supabase_db:
            print("⚠️ Supabase non initialisé.")
            return

        try:
            now = datetime.now(timezone.utc)
            RetargetingService._process_reminder_1(now)
            RetargetingService._process_reminder_2(now)
            RetargetingService._expire_stale_carts(now)
        except Exception as e:
            print(f"❌ Erreur lors du retargeting : {e}")