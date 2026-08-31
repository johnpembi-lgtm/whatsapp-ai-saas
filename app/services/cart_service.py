import logging
from datetime import datetime, timezone
from app.core.database import supabase_db

logger = logging.getLogger(__name__)


class CartService:

    @staticmethod
    def is_order_completed(phone_number_id: str, customer_phone: str) -> bool:
        """Vérifie si le statut de la commande est marqué comme 'completed' dans Supabase."""
        if not supabase_db:
            return False
        try:
            response = (
                supabase_db.table("cart_tracking")
                .select("status")
                .eq("phone_number_id", str(phone_number_id).strip())
                .eq("customer_phone", str(customer_phone).strip())
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0].get("status") == "completed"
        except Exception as e:
            logger.error(f"❌ Erreur lors de la vérification du statut panier : {e}")
        return False

    @staticmethod
    def update_interaction(phone_number_id: str, customer_phone: str, last_product: str = None):
        """
        Met à jour l'interaction client en UN SEUL appel Supabase (sans SELECT préalable).
        Si la commande est marquée 'completed', aucune mise à jour n'est effectuée.
        """
        if not supabase_db:
            return

        clean_phone_id = str(phone_number_id).strip()
        clean_customer = str(customer_phone).strip().replace("+", "").replace(" ", "")
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            # 1. Préparation des données de mise à jour / réinitialisation
            update_payload = {
                "last_interaction": now_iso,
                "status": "pending",
                "reminder_count": 0,
            }
            if last_product:
                update_payload["last_product"] = last_product

            # 2. UPDATE conditionnel direct : ne modifie QUE si status != 'completed'
            res = (
                supabase_db.table("cart_tracking")
                .update(update_payload)
                .eq("phone_number_id", clean_phone_id)
                .eq("customer_phone", clean_customer)
                .neq("status", "completed")  # Filtre SQL direct côté Supabase
                .execute()
            )

            # 3. Si aucune ligne n'a été modifiée, on vérifie si le panier existe ou s'il s'agit d'un nouveau client
            if not res.data:
                if not CartService.is_order_completed(clean_phone_id, clean_customer):
                    new_cart = {
                        "phone_number_id": clean_phone_id,
                        "customer_phone": clean_customer,
                        "last_interaction": now_iso,
                        "status": "pending",
                        "reminder_count": 0,
                    }
                    if last_product:
                        new_cart["last_product"] = last_product

                    supabase_db.table("cart_tracking").insert(new_cart).execute()

        except Exception as e:
            logger.error(f"❌ Erreur lors de la mise à jour de l'interaction panier : {e}")

    @staticmethod
    def mark_as_completed(phone_number_id: str, customer_phone: str):
        """Marque une commande comme finalisée sur Supabase pour annuler les relances."""
        if not supabase_db:
            return
        try:
            supabase_db.table("cart_tracking") \
                .update({"status": "completed"}) \
                .eq("phone_number_id", str(phone_number_id).strip()) \
                .eq("customer_phone", str(customer_phone).strip().replace("+", "").replace(" ", "")) \
                .execute()
        except Exception as e:
            logger.error(f"❌ Erreur lors de la validation du panier : {e}")