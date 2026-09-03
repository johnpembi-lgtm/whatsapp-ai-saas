import logging
from datetime import datetime, timezone
from app.core.database import (
    supabase_db,
    _get_tenant_id,
    _get_or_create_customer,
    get_or_create_cart,
    get_cart_items,
    set_cart_item,
    clear_cart_items,
)

logger = logging.getLogger(__name__)


class CartService:
    """Gestionnaire de panier multi-tenant canonique (Supabase) sans état en mémoire volatile."""

    @staticmethod
    def _resolve_context(phone_number_id: str, customer_phone: str):
        """Résout le tenant_id, customer_id et cart actif dans la base de données."""
        if not supabase_db:
            return None, None, None

        tenant_id = _get_tenant_id(phone_number_id)
        if not tenant_id:
            return None, None, None

        customer_id = _get_or_create_customer(tenant_id, customer_phone)
        if not customer_id:
            return None, None, None

        cart = get_or_create_cart(tenant_id, customer_id)
        return tenant_id, customer_id, cart

    @staticmethod
    def clear_cart(phone_number_id: str, customer_phone: str):
        """Vide tous les articles du panier client dans Supabase."""
        tenant_id, customer_id, cart = CartService._resolve_context(phone_number_id, customer_phone)
        if cart:
            clear_cart_items(cart["id"])
            logger.info(f"🗑️ Panier vidé sur Supabase pour le client {customer_phone}.")

    @staticmethod
    def add_item(
        phone_number_id: str,
        sender_phone: str,
        product_id: str,
        product_name: str,
        price: float,
        quantity: int = 1,
    ):
        """Ajoute ou met à jour la quantité d'un produit dans la table `cart_items`."""
        tenant_id, customer_id, cart = CartService._resolve_context(phone_number_id, sender_phone)
        if not cart:
            logger.error("❌ Impossible d'initialiser le panier Supabase.")
            return

        cart_id = cart["id"]

        # Récupération des articles existants pour calculer l'incrément
        existing_items = get_cart_items(cart_id)
        current_qty = 0
        for item in existing_items:
            if item.get("product_id") == product_id:
                current_qty = item.get("quantity", 0)
                break

        new_qty = current_qty + quantity
        set_cart_item(cart_id, product_id, new_qty, price)

        # Mettre à jour la date de dernière interaction du panier
        CartService.update_interaction(phone_number_id, sender_phone, last_product=product_name)

    @staticmethod
    def get_cart(phone_number_id: str, customer_phone: str) -> list:
        """
        Récupère les articles du panier canonique depuis Supabase.
        Retourne une liste au format attendu par la logique métier.
        """
        tenant_id, customer_id, cart = CartService._resolve_context(phone_number_id, customer_phone)
        if not cart:
            return []

        raw_items = get_cart_items(cart["id"])
        formatted_items = []

        for item in raw_items:
            product = item.get("products") or {}
            formatted_items.append({
                "product_id": item["product_id"],
                "product_name": product.get("name", "Produit inconnu"),
                "price": float(item.get("unit_price", 0.0)),
                "quantity": item.get("quantity", 1),
            })

        return formatted_items

    @staticmethod
    def is_order_completed(phone_number_id: str, customer_phone: str) -> bool:
        """Vérifie si le panier du client est marqué comme 'completed' dans Supabase."""
        tenant_id, customer_id, cart = CartService._resolve_context(phone_number_id, customer_phone)
        if not cart:
            return False
        return cart.get("status") == "completed"

    @staticmethod
    def update_interaction(phone_number_id: str, customer_phone: str, last_product: str = None):
        """Met à jour l'horodatage de dernière interaction du panier actif."""
        if not supabase_db:
            return

        tenant_id, customer_id, cart = CartService._resolve_context(phone_number_id, customer_phone)
        if not cart or cart.get("status") == "completed":
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        update_payload = {
            "last_interaction": now_iso,
            "status": "pending",
            "reminder_count": 0,
            "updated_at": now_iso,
        }

        try:
            supabase_db.table("carts").update(update_payload).eq("id", cart["id"]).execute()
        except Exception as e:
            logger.error(f"❌ Erreur lors de la mise à jour de l'interaction panier : {e}")

    @staticmethod
    def mark_as_completed(phone_number_id: str, customer_phone: str):
        """Marque le panier comme 'completed' dans Supabase lors de la validation."""
        tenant_id, customer_id, cart = CartService._resolve_context(phone_number_id, customer_phone)
        if not cart:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            supabase_db.table("carts").update({
                "status": "completed",
                "updated_at": now_iso,
            }).eq("id", cart["id"]).execute()
            logger.info(f"✅ Panier marqué comme complété pour {customer_phone} (Tenant {phone_number_id})")
        except Exception as e:
            logger.error(f"❌ Erreur lors de la finalisation du panier : {e}")