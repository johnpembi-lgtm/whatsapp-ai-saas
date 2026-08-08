import os
from datetime import datetime, timedelta
from flask import current_app
from app.core.database import get_db_connection
from app.core.tenant_manager import TenantManager
from app.services.whatsapp_service import WhatsAppService

class RetargetingService:
    @staticmethod
    def process_abandoned_carts():
        """Recherche et relance les prospects inactifs entre 2h et 22h."""
        try:
            # Utilisation d'une heure naïve ou UTC selon votre standard de base de données
            now = datetime.utcnow()
            min_time = (now - timedelta(hours=22)).strftime("%Y-%m-%d %H:%M:%S")
            max_time = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

            print(f"⏰ [SCHEDULER] Scan des paniers abandonnés entre {min_time} et {max_time}...")

            with get_db_connection() as conn:
                # Assure l'accès par dictionnaire si ce n'est pas fait globalement
                try:
                    conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
                except AttributeError:
                    pass # Si l'objet ne permet pas la mutation directe du row_factory

                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, phone_number_id, customer_phone, last_product 
                    FROM cart_tracking 
                    WHERE status = 'pending' 
                    AND last_interaction BETWEEN ? AND ?
                """, (min_time, max_time))

                pending_carts = cursor.fetchall()

                if not pending_carts:
                    print("📋 Aucun panier abandonné à relancer pour le moment.")
                    return

                # Liste pour stocker les IDs mis à jour avec succès
                successful_reminders = []

                for cart in pending_carts:
                    # Gestion de secours si row_factory n'est pas un dictionnaire
                    if isinstance(cart, tuple):
                        cart_id, phone_number_id, customer_phone, last_product = cart
                    else:
                        cart_id = cart["id"]
                        phone_number_id = cart["phone_number_id"]
                        customer_phone = cart["customer_phone"]
                        last_product = cart["last_product"]

                    tenant = TenantManager.get_tenant_by_phone_id(phone_number_id)
                    if not tenant:
                        print(f"⚠️ Tenant introuvable pour le phone_number_id : {phone_number_id}")
                        continue

                    store_name = tenant.get("store_name", tenant.get("store_id", "notre boutique"))
                    
                    # Personnalisation dynamique du message
                    if last_product:
                        message = f"Bonjour ! 👋 Avez-vous eu le temps de réfléchir concernant le produit *{last_product}* chez *{store_name}* ? Je reste à votre disposition si vous avez la moindre question !"
                    else:
                        message = f"Bonjour ! 👋 Je reste disponible si vous avez besoin d'informations complémentaires sur nos articles chez *{store_name}*."

                    # --- CORRECTION CASCADE DU TOKEN ---
                    access_token = (
                        tenant.get("whatsapp_access_token") 
                        or current_app.config.get("WHATSAPP_ACCESS_TOKEN")
                        or os.getenv("WHATSAPP_ACCESS_TOKEN")
                    )

                    res = WhatsAppService.send_message(
                        phone_number_id=phone_number_id,
                        recipient_phone=customer_phone,
                        message_text=message,
                        access_token=access_token
                    )

                    # Si l'envoi WhatsApp est validé par l'API Meta
                    if res and ("messages" in res or "messaging_product" in res):
                        successful_reminders.append(cart_id)
                        print(f"🚀 Relance programmée validée pour +{customer_phone} ({store_name})")

                # Application des changements en une seule fois pour éviter les locks SQLite
                if successful_reminders:
                    for c_id in successful_reminders:
                        cursor.execute("UPDATE cart_tracking SET status = 'reminded' WHERE id = ?", (c_id,))
                    conn.commit()
                    print(f"✅ {len(successful_reminders)} panier(s) mis à jour au statut 'reminded'.")

        except Exception as e:
            print(f"❌ Erreur lors de l'exécution du retargeting : {e}")