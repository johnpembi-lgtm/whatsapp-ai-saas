from datetime import datetime, timezone
from app.core.database import supabase_db

class CartService:
    @staticmethod
    def is_order_completed(phone_number_id, customer_phone):
        """Vérifie si le statut de la commande est marqué comme 'completed' dans Supabase."""
        if not supabase_db:
            return False
        try:
            response = supabase_db.table("cart_tracking") \
                .select("status") \
                .eq("phone_number_id", str(phone_number_id)) \
                .eq("customer_phone", str(customer_phone)) \
                .execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0].get("status") == "completed"
        except Exception as e:
            print(f"❌ Erreur lors de la vérification du statut panier : {e}")
        return False

    @staticmethod
    def update_interaction(phone_number_id, customer_phone, last_product=None):
        """Met à jour l'horodatage de la dernière interaction dans Supabase (uniquement si non complétée)."""
        if not supabase_db:
            return
        try:
            # Ne réactive pas en statut pending si la commande est déjà validée
            if CartService.is_order_completed(phone_number_id, customer_phone):
                return

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