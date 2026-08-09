import os
from datetime import datetime, timedelta, timezone
from flask import current_app
from app.core.database import supabase_db
from app.core.tenant_manager import TenantManager
from app.services.whatsapp_service import WhatsAppService

class RetargetingService:
    @staticmethod
    def process_abandoned_carts():
        """Recherche et relance les prospects inactifs entre 2h et 22h via Supabase."""
        if not supabase_db:
            print("⚠️ Supabase non initialisé.")
            return

        try:
            now = datetime.now(timezone.utc)
            min_time = (now - timedelta(hours=22)).isoformat()
            max_time = (now - timedelta(hours=2)).isoformat()

            print(f"⏰ [SCHEDULER] Scan des paniers abandonnés entre {min_time} et {max_time}...")

            res = supabase_db.table("cart_tracking") \
                .select("id, phone_number_id, customer_phone, last_product") \
                .eq("status", "pending") \
                .gte("last_interaction", min_time) \
                .lte("last_interaction", max_time) \
                .execute()

            pending_carts = res.data or []

            if not pending_carts:
                print("📋 Aucun panier abandonné à relancer pour le moment.")
                return

            for cart in pending_carts:
                cart_id = cart["id"]
                phone_number_id = cart["phone_number_id"]
                customer_phone = cart["customer_phone"]
                last_product = cart.get("last_product")

                tenant = TenantManager.get_tenant_by_phone_id(phone_number_id)
                if not tenant:
                    print(f"⚠️ Tenant introuvable pour le phone_number_id : {phone_number_id}")
                    continue

                store_name = tenant.get("store_name", tenant.get("store_id", "notre boutique"))
                
                if last_product:
                    message = f"Bonjour ! 👋 Avez-vous eu le temps de réfléchir concernant le produit *{last_product}* chez *{store_name}* ? Je reste à votre disposition si vous avez la moindre question !"
                else:
                    message = f"Bonjour ! 👋 Je reste disponible si vous avez besoin d'informations complémentaires sur nos articles chez *{store_name}*."

                access_token = (
                    tenant.get("whatsapp_access_token") 
                    or current_app.config.get("WHATSAPP_ACCESS_TOKEN")
                    or os.getenv("WHATSAPP_ACCESS_TOKEN")
                )

                res_wa = WhatsAppService.send_message(
                    phone_number_id=phone_number_id,
                    recipient_phone=customer_phone,
                    message_text=message,
                    access_token=access_token
                )

                if res_wa and ("messages" in res_wa or "messaging_product" in res_wa):
                    supabase_db.table("cart_tracking") \
                        .update({"status": "reminded"}) \
                        .eq("id", cart_id) \
                        .execute()
                    print(f"🚀 Relance programmée validée pour +{customer_phone} ({store_name})")

        except Exception as e:
            print(f"❌ Erreur lors de l'exécution du retargeting : {e}")