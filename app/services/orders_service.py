import datetime
import logging
from typing import Dict, Any, List, Optional
from app.core.database import (
    supabase_db,
    get_product_by_name_or_id,
    create_order_with_items,
    _get_or_create_customer,
)

logger = logging.getLogger(__name__)


class OrdersService:
    """Service d'analyse, de validation, d'enregistrement et de mise à jour des commandes clients."""

    @staticmethod
    def create_order(
        tenant_id: str,
        customer_phone: str,
        items: list,
        delivery_type: str = "pickup",
        delivery_address: Optional[str] = None,
        customer_name: str = "Client",
        location_data: Optional[dict] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        external_reference: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Création de commande acceptant l'ensemble des arguments requis par les tests Phase 4.
        """
        if not tenant_id:
            return {"success": False, "error": "tenant_id missing"}

        # 1. Vérification de l'existence du tenant et de ses configurations
        tenant_res = (
            supabase_db.table("tenants")
            .select("*")
            .eq("id", tenant_id)
            .execute()
        )
        if not tenant_res.data:
            return {"success": False, "error": "tenant_not_found"}

        tenant = tenant_res.data[0]
        delivery_enabled = tenant.get("delivery_enabled", True)
        pickup_enabled = tenant.get("pickup_enabled", True)

        raw_type = (delivery_type or "pickup").lower()
        if raw_type == "delivery" and not delivery_enabled:
            return {
                "success": False,
                "status": "rejected",
                "reason": "delivery_disabled",
            }

        if raw_type == "pickup" and not pickup_enabled:
            return {
                "success": False,
                "status": "rejected",
                "reason": "pickup_disabled",
            }

        fulfillment_type = raw_type

        # Extraction / Normalisation des coordonnées GPS
        loc = location_data or {}
        final_lat = latitude if latitude is not None else loc.get("latitude")
        final_lng = longitude if longitude is not None else loc.get("longitude")

        # Validation de l'adresse ou des coordonnées GPS en mode livraison
        if fulfillment_type == "delivery":
            if not delivery_address and final_lat is None and final_lng is None:
                return {
                    "success": False,
                    "status": "rejected",
                    "reason": "missing_address_or_location",
                    "error": "Adresse ou géolocalisation requise pour la livraison",
                }

        # 2. Gestion de l'idempotence via external_reference
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        ext_ref = (
            external_reference
            or f"ORD-{tenant_id[:8]}-{customer_phone[-4:]}-{int(now_dt.timestamp())}"
        )

        if external_reference:
            existing = (
                supabase_db.table("orders")
                .select("*")
                .eq("tenant_id", tenant_id)
                .eq("external_reference", external_reference)
                .execute()
            )
            if existing.data and len(existing.data) > 0:
                existing_order = existing.data[0]
                return {
                    "success": True,
                    "order_id": existing_order.get("id"),
                    "total_amount": existing_order.get("total_amount"),
                    "order": existing_order,
                    "idempotent": True,
                }

        # 3. Calcul du total et résolution des produits
        calculated_total = 0.0
        resolved_items = []

        for item in items:
            p_id = item.get("product_id") or item.get("id") or item.get("name")
            qty = max(1, int(item.get("quantity", 1)))

            prod = get_product_by_name_or_id(tenant_id, str(p_id))
            if prod:
                db_price = float(prod.get("price", item.get("price", 0.0)))
                calculated_total += db_price * qty
                resolved_items.append(
                    {
                        "product_id": prod["id"],
                        "quantity": qty,
                        "unit_price": db_price,
                        "product_name": prod.get("name"),
                    }
                )

        if not resolved_items:
            return {
                "success": False,
                "status": "rejected",
                "reason": "no_valid_products",
            }

        # 4. Identification du client
        customer_id = _get_or_create_customer(
            tenant_id, customer_phone, full_name=customer_name
        )

        addr_str = (
            delivery_address
            if fulfillment_type == "delivery"
            else "Retrait en magasin"
        )

        # 5. Construction du payload de la commande
        order_payload = {
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "status": "pending",
            "fulfillment_type": fulfillment_type,
            "delivery_address": addr_str,
            "total_amount": calculated_total,
            "external_reference": ext_ref,
            "details": {
                "items": resolved_items,
                "fulfillment_type": fulfillment_type,
                "delivery_address": addr_str,
                "client_name": customer_name,
                "client_phone": customer_phone,
            },
        }

        if final_lat is not None:
            order_payload["delivery_latitude"] = final_lat
        if final_lng is not None:
            order_payload["delivery_longitude"] = final_lng

        if final_lat is not None or final_lng is not None:
            order_payload["details"]["location_data"] = {
                "latitude": final_lat,
                "longitude": final_lng,
            }

        # 6. Insertion en base de données
        try:
            created_order = create_order_with_items(order_payload, resolved_items)
            order_id = created_order.get("id") if created_order else None
            return {
                "success": True,
                "order_id": order_id,
                "total_amount": calculated_total,
                "order": created_order,
            }
        except Exception as e:
            logger.error(f"❌ Erreur lors de la création de commande : {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def update_order_status(
        order_id: str,
        tenant_id: str,
        new_status: str
    ) -> Dict[str, Any]:
        """
        Met à jour le statut d'une commande tout en gérant les timestamps
        'completed_at' / 'cancelled_at' et la décrémentation idempotente du stock via 'stock_applied_at'.
        """
        # 1. Vérification de l'existence de la commande
        existing_res = (
            supabase_db.table("orders")
            .select("*")
            .eq("id", order_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )

        if not existing_res.data:
            logger.warning(
                f"⚠️ Tentative de mise à jour échouée pour order_id={order_id}, tenant_id={tenant_id}"
            )
            return {
                "success": False,
                "updated": 0,
                "error": "Order not found or tenant mismatch",
            }

        current_order = existing_res.data[0]
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        update_payload: Dict[str, Any] = {"status": new_status}

        # 2. Gestion idempotente des Timestamps
        if new_status == "completed" and not current_order.get("completed_at"):
            update_payload["completed_at"] = now_iso
        elif new_status == "cancelled" and not current_order.get("cancelled_at"):
            update_payload["cancelled_at"] = now_iso

        # 3. Décrémentation du stock unique (Seulement si stock_applied_at est NULL)
        stock_already_applied = current_order.get("stock_applied_at") is not None

        if new_status == "completed" and not stock_already_applied:
            # Tente de récupérer depuis les articles structurés ou la clef details JSONB
            items = current_order.get("details", {}).get("items", [])
            if not items:
                # Fetch fallback depuis order_items si présent
                order_items_res = (
                    supabase_db.table("order_items")
                    .select("*")
                    .eq("order_id", order_id)
                    .execute()
                )
                items = order_items_res.data or []

            for item in items:
                p_id = item.get("product_id")
                qty = item.get("quantity", 0)
                if p_id and qty > 0:
                    prod_res = (
                        supabase_db.table("products")
                        .select("stock")
                        .eq("id", p_id)
                        .execute()
                    )
                    if prod_res.data:
                        current_stock = prod_res.data[0].get("stock", 0)
                        new_stock = max(0, current_stock - qty)
                        supabase_db.table("products").update(
                            {"stock": new_stock}
                        ).eq("id", p_id).execute()

            # Marquer la commande comme ayant déjà appliqué son stock
            update_payload["stock_applied_at"] = now_iso

        # 4. Mise à jour de la commande dans Supabase
        update_res = (
            supabase_db.table("orders")
            .update(update_payload)
            .eq("id", order_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )

        if not update_res.data:
            return {"success": False, "updated": 0}

        return {"success": True, "updated": 1, "order": update_res.data[0]}

    @staticmethod
    def get_order_by_id(order_id: str) -> Optional[Dict[str, Any]]:
        """Récupère une commande par son identifiant unique."""
        res = supabase_db.table("orders").select("*").eq("id", order_id).execute()
        if res.data:
            return res.data[0]
        return None