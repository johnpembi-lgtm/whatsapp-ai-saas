from datetime import datetime, timezone
from app.core.database import supabase_db

class CartService:
    @staticmethod
    def update_interaction(phone_number_id, customer_phone, last_product=None):
        """Met à jour l'horodatage de la dernière interaction dans Supabase (Upsert)."""
        if not supabase_db:
            return
        try:
            now = datetime.now(timezone.utc).isoformat()
            payload = {
                "phone_number_id": str(phone_number_id),
                "customer_phone": str(customer_phone),
                "last_interaction": now,
                "status": "pending"
            }
            if last_product:
                payload["last_product"] = last_product

            supabase_db.table("cart_tracking").upsert(
                payload,
                on_conflict="phone_number_id,customer_phone"
            ).execute()
        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour de l'interaction panier : {e}")

    @staticmethod
    def mark_as_completed(phone_number_id, customer_phone):
        """Marque une commande comme finalisée sur Supabase pour annuler les relances."""
        if not supabase_db:
            return
        try:
            supabase_db.table("cart_tracking") \
                .update({"status": "completed"}) \
                .eq("phone_number_id", str(phone_number_id)) \
                .eq("customer_phone", str(customer_phone)) \
                .execute()
        except Exception as e:
            print(f"❌ Erreur lors de la validation du panier : {e}")