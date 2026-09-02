import logging
from datetime import datetime, timezone
from app.core.database import supabase_db

logger = logging.getLogger(__name__)


class CartService:
    """Gestionnaire de panier multi-tenant hermétique et de suivi d'interactions."""

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
        Met à jour l'interaction client isolée par (phone_number_id, customer_phone).
        Ne modifie pas les paniers marqués 'completed'.
        """
        if not supabase_db:
            return

        clean_phone_id = str(phone_number_id).strip()
        clean_customer = str(customer_phone).strip().replace("+", "").replace(" ", "")
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            update_payload = {
                "last_interaction": now_iso,
                "status": "pending",
                "reminder_count": 0,
            }
            if last_product:
                update_payload["last_product"] = last_product

            # Mise à jour filtrée directement en base par couple (tenant, client)
            res = (
                supabase_db.table("cart_tracking")
                .update(update_payload)
                .eq("phone_number_id", clean_phone_id)
                .eq("customer_phone", clean_customer)
                .neq("status", "completed")
                .execute()
            )

            # Si aucune ligne mise à jour et panier non finalisé, création du panier
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
import logging
from datetime import datetime, timezone
from app.core.database import supabase_db

logger = logging.getLogger(__name__)


class CartService:
    """Gestionnaire de panier multi-tenant hermétique et de suivi d'interactions."""

    # Stockage temporaire en mémoire pour les paniers actifs
    # Clé: "phone_number_id:customer_phone" -> Valeur: liste d'articles
    _carts = {}

    @staticmethod
    def clear_cart(phone_number_id: str, customer_phone: str):
        """Vide le panier d'un client spécifique pour un tenant donné."""
        key = f"{str(phone_number_id).strip()}:{str(customer_phone).strip()}"
        CartService._carts.pop(key, None)

    @staticmethod
    def add_item(phone_number_id: str, sender_phone: str, product_id: str, product_name: str, price: float, quantity: int = 1):
        """Ajoute un article dans le panier isolé d'un client."""
        key = f"{str(phone_number_id).strip()}:{str(sender_phone).strip()}"
        if key not in CartService._carts:
            CartService._carts[key] = []
        
        # Mise à jour si le produit existe déjà, sinon ajout
        for item in CartService._carts[key]:
            if item["product_id"] == product_id:
                item["quantity"] += quantity
                return
                
        CartService._carts[key].append({
            "product_id": product_id,
            "product_name": product_name,
            "price": price,
            "quantity": quantity
        })
        
        # Met à jour le suivi de relance Supabase
        CartService.update_interaction(phone_number_id, sender_phone, last_product=product_name)

    @staticmethod
    def get_cart(phone_number_id: str, customer_phone: str) -> list:
        """Récupère le panier isolé d'un client."""
        key = f"{str(phone_number_id).strip()}:{str(customer_phone).strip()}"
        return CartService._carts.get(key, [])

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
        Met à jour l'interaction client isolée par (phone_number_id, customer_phone).
        Ne modifie pas les paniers marqués 'completed'.
        """
        if not supabase_db:
            return

        clean_phone_id = str(phone_number_id).strip()
        clean_customer = str(customer_phone).strip().replace("+", "").replace(" ", "")
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            update_payload = {
                "last_interaction": now_iso,
                "status": "pending",
                "reminder_count": 0,
            }
            if last_product:
                update_payload["last_product"] = last_product

            res = (
                supabase_db.table("cart_tracking")
                .update(update_payload)
                .eq("phone_number_id", clean_phone_id)
                .eq("customer_phone", clean_customer)
                .neq("status", "completed")
                .execute()
            )

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
        """Marque une commande comme finalisée sur Supabase pour stopper les relances."""
        if not supabase_db:
            return
        try:
            supabase_db.table("cart_tracking") \
                .update({"status": "completed"}) \
                .eq("phone_number_id", str(phone_number_id).strip()) \
                .eq("customer_phone", str(customer_phone).strip().replace("+", "").replace(" ", "")) \
                .execute()
            logger.info(f"✅ Panier marqué comme complété pour {customer_phone} (Tenant {phone_number_id})")
        except Exception as e:
            logger.error(f"❌ Erreur lors de la validation du panier : {e}")
    @staticmethod
    def mark_as_completed(phone_number_id: str, customer_phone: str):
        """Marque une commande comme finalisée sur Supabase pour stopper les relances."""
        if not supabase_db:
            return
        try:
            supabase_db.table("cart_tracking") \
                .update({"status": "completed"}) \
                .eq("phone_number_id", str(phone_number_id).strip()) \
                .eq("customer_phone", str(customer_phone).strip().replace("+", "").replace(" ", "")) \
                .execute()
            logger.info(f"✅ Panier marqué comme complété pour {customer_phone} (Tenant {phone_number_id})")
        except Exception as e:
            logger.error(f"❌ Erreur lors de la validation du panier : {e}")