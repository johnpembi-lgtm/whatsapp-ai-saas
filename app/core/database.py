import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Chargement sécurisé du fichier .env
env_path = Path(__file__).resolve().parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(dotenv_path=env_path, override=True)

logger = logging.getLogger(__name__)

raw_url = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_URL = raw_url.split("/rest/v1")[0].rstrip("/") if raw_url else ""

# -----------------------------------------------------------------------------
# SÉPARATION ACCÈS BACKEND (SERVICE_ROLE) vs CLIENT (ANON)
# -----------------------------------------------------------------------------
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_KEY", "").strip() or os.getenv("SUPABASE_ANON_KEY", "").strip()

supabase_db: Client = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    try:
        supabase_db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        logger.info("✅ Client Supabase Admin (Service Role) initialisé avec succès.")
    except Exception as e:
        logger.error(f"❌ Échec de la connexion Admin Supabase : {e}")
        supabase_db = None
elif SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase_db = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        logger.warning("⚠️ Client Supabase initialisé avec ANON_KEY (Sujet aux restrictions RLS).")
    except Exception as e:
        logger.error(f"❌ Échec de la connexion Supabase : {e}")
        supabase_db = None
else:
    logger.error("❌ Variables SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquantes.")


def get_anon_supabase_client() -> Client:
    """Retourne un client de test soumis aux règles RLS (via Anon Key)."""
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    raise ValueError("SUPABASE_URL ou SUPABASE_ANON_KEY non configurée.")


def init_db():
    """Compatibilité d'initialisation."""
    pass


# ==========================================
# UTILITAIRES DE RÉSOLUTIONS DES IDS CANONIQUES
# ==========================================

def _clean_phone(phone: str) -> str:
    """Normalise les numéros de téléphone en supprimant les espaces et le '+'."""
    if not phone:
        return ""
    return str(phone).strip().replace("+", "").replace(" ", "")


def _get_tenant_id(whatsapp_phone_number_id: str) -> str:
    """Récupère l'UUID du tenant à partir de son whatsapp_phone_number_id."""
    if not supabase_db or not whatsapp_phone_number_id:
        return None
    clean_phone_id = _clean_phone(whatsapp_phone_number_id)
    try:
        res = supabase_db.table("tenants") \
            .select("id") \
            .eq("whatsapp_phone_number_id", clean_phone_id) \
            .execute()
        if res and hasattr(res, "data") and res.data:
            return res.data[0]["id"]
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération du tenant_id : {e}")
    return None


def _get_or_create_customer(tenant_id: str, phone: str, full_name: str = None) -> str:
    """
    Récupère ou crée le client (table `customers`).
    Utilise upsert atomique pour parer aux conditions de course multi-threads.
    """
    if not supabase_db or not tenant_id or not phone:
        return None
    clean_phone = _clean_phone(phone)
    payload = {
        "tenant_id": tenant_id,
        "phone": clean_phone,
        "full_name": full_name or clean_phone
    }
    try:
        # Upsert atomique basé sur la contrainte d'unicité (tenant_id, phone)
        res = supabase_db.table("customers").upsert(
            payload,
            on_conflict="tenant_id,phone"
        ).execute()

        if res and hasattr(res, "data") and res.data:
            customer = res.data[0]
            return customer["id"]
    except Exception as e:
        logger.error(f"❌ Erreur lors de la résolution/création du customer_id : {e}")
    return None


def _get_or_create_conversation(tenant_id: str, customer_id: str) -> str:
    """Récupère ou crée la conversation canonique pour un couple (tenant, customer)."""
    if not supabase_db or not tenant_id or not customer_id:
        return None
    try:
        res = supabase_db.table("conversations").upsert(
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "status": "active"
            },
            on_conflict="tenant_id,customer_id"
        ).execute()
        
        if res and hasattr(res, "data") and res.data:
            return res.data[0]["id"]
    except Exception as e:
        logger.error(f"❌ Erreur lors de la résolution de la conversation : {e}")
    return None


# ==========================================
# GESTION DES MESSAGES / HISTORIQUE CANONIQUE
# ==========================================

def save_message(whatsapp_phone_number_id, user_phone, role, content, wam_id=None):
    """Enregistre un message dans la table canonique `messages`."""
    if not supabase_db:
        return
    try:
        tenant_id = _get_tenant_id(whatsapp_phone_number_id)
        if not tenant_id:
            return
        customer_id = _get_or_create_customer(tenant_id, user_phone)
        if not customer_id:
            return
        conversation_id = _get_or_create_conversation(tenant_id, customer_id)
        if not conversation_id:
            return

        sender_type = "user" if role in ("user", "client") else "assistant"

        payload = {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "sender_type": sender_type,
            "content": content
        }
        if wam_id:
            payload["wam_id"] = str(wam_id)

        supabase_db.table("messages").insert(payload).execute()

        supabase_db.table("conversations").update({
            "last_interaction_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", conversation_id).execute()

    except Exception as e:
        logger.error(f"❌ Erreur lors de la sauvegarde du message sur Supabase : {e}")


def get_conversation_history(whatsapp_phone_number_id, user_phone, limit=6):
    """Récupère l'historique chronologique des conversations."""
    if not supabase_db:
        return []
    try:
        tenant_id = _get_tenant_id(whatsapp_phone_number_id)
        if not tenant_id:
            return []
        customer_id = _get_or_create_customer(tenant_id, user_phone)
        if not customer_id:
            return []
        conversation_id = _get_or_create_conversation(tenant_id, customer_id)
        if not conversation_id:
            return []

        res = supabase_db.table("messages") \
            .select("sender_type, content, created_at") \
            .eq("conversation_id", conversation_id) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()

        if not res or not hasattr(res, "data") or not res.data:
            return []

        history = [
            {
                "role": "user" if row["sender_type"] == "user" else "assistant",
                "content": row["content"]
            }
            for row in res.data
        ]
        history.reverse()
        return history
    except Exception as e:
        logger.error(f"❌ Erreur de récupération d'historique sur Supabase : {e}")
        return []


# ==========================================
# GESTION DES PANIERS CANONIQUES (SUPABASE)
# ==========================================

def get_or_create_cart(tenant_id: str, customer_id: str) -> dict:
    """Récupère ou crée le panier actif (status='pending') pour un client."""
    if not supabase_db or not tenant_id or not customer_id:
        return None
    try:
        res = supabase_db.table("carts") \
            .select("*") \
            .eq("tenant_id", tenant_id) \
            .eq("customer_id", customer_id) \
            .eq("status", "pending") \
            .execute()
        if res and hasattr(res, "data") and res.data:
            return res.data[0]

        now_iso = datetime.now(timezone.utc).isoformat()
        ins = supabase_db.table("carts").insert({
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "status": "pending",
            "last_interaction": now_iso
        }).execute()
        if ins and hasattr(ins, "data") and ins.data:
            return ins.data[0]
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération/création du panier : {e}")
    return None


def get_cart_items(cart_id: str) -> list:
    """Récupère les articles d'un panier avec les détails du produit."""
    if not supabase_db or not cart_id:
        return []
    try:
        res = supabase_db.table("cart_items") \
            .select("*, products(*)") \
            .eq("cart_id", cart_id) \
            .execute()
        return res.data if res and hasattr(res, "data") and res.data else []
    except Exception as e:
        logger.error(f"❌ Erreur de lecture des cart_items : {e}")
        return []


def set_cart_item(cart_id: str, product_id: str, quantity: int, unit_price: float):
    """Ajoute ou met à jour la quantité d'un produit dans le panier."""
    if not supabase_db or not cart_id or not product_id:
        return
    try:
        if quantity <= 0:
            supabase_db.table("cart_items") \
                .delete() \
                .eq("cart_id", cart_id) \
                .eq("product_id", product_id) \
                .execute()
        else:
            supabase_db.table("cart_items").upsert({
                "cart_id": cart_id,
                "product_id": product_id,
                "quantity": quantity,
                "unit_price": unit_price
            }, on_conflict="cart_id,product_id").execute()
    except Exception as e:
        logger.error(f"❌ Erreur lors de la modification de cart_item : {e}")


def clear_cart_items(cart_id: str):
    """Vide tous les articles d'un panier."""
    if not supabase_db or not cart_id:
        return
    try:
        supabase_db.table("cart_items").delete().eq("cart_id", cart_id).execute()
    except Exception as e:
        logger.error(f"❌ Erreur lors du vidage du panier : {e}")


def update_cart_tracking(whatsapp_phone_number_id, customer_phone, last_product=None, status='pending'):
    """Met à jour l'horodatage et le statut du panier actif."""
    if not supabase_db:
        return
    try:
        tenant_id = _get_tenant_id(whatsapp_phone_number_id)
        if not tenant_id:
            return
        customer_id = _get_or_create_customer(tenant_id, customer_phone)
        if not customer_id:
            return

        cart = get_or_create_cart(tenant_id, customer_id)
        if not cart:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "status": status,
            "last_interaction": now_iso,
            "updated_at": now_iso
        }

        supabase_db.table("carts").update(payload).eq("id", cart["id"]).execute()

    except Exception as e:
        logger.error(f"❌ Erreur lors de la mise à jour du panier sur Supabase : {e}")


def get_pending_carts_for_retry(limit=10):
    """Récupère les paniers en attente pour les relances automatiques."""
    if not supabase_db:
        return []
    try:
        res = supabase_db.table("carts") \
            .select("*, tenants(whatsapp_phone_number_id), customers(phone)") \
            .eq("status", "pending") \
            .limit(limit) \
            .execute()

        if not res or not hasattr(res, "data") or not res.data:
            return []

        pending_carts = []
        for row in res.data:
            pending_carts.append({
                "id": row["id"],
                "tenant_id": row["tenant_id"],
                "customer_id": row["customer_id"],
                "whatsapp_phone_number_id": row.get("tenants", {}).get("whatsapp_phone_number_id"),
                "customer_phone": row.get("customers", {}).get("phone"),
                "status": row["status"],
                "reminder_count": row.get("reminder_count", 0),
                "last_interaction": row.get("last_interaction")
            })
        return pending_carts
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération des paniers en attente : {e}")
        return []


# ==========================================
# GESTION DES COMMANDES & STOCK
# ==========================================

def get_product_by_name_or_id(tenant_id: str, identifier: str) -> dict:
    """Recherche un produit par ID ou par nom exact/partiel."""
    if not supabase_db or not tenant_id or not identifier:
        return None
    try:
        res = supabase_db.table("products").select("*").eq("tenant_id", tenant_id).eq("id", str(identifier)).execute()
        if res and hasattr(res, "data") and res.data:
            return res.data[0]

        res = supabase_db.table("products").select("*").eq("tenant_id", tenant_id).ilike("name", f"%{identifier}%").execute()
        if res and hasattr(res, "data") and res.data:
            return res.data[0]
    except Exception as e:
        logger.error(f"❌ Erreur lors de la recherche du produit : {e}")
    return None


def get_order_by_external_reference(external_reference: str, tenant_id: str) -> dict | None:
    """
    Récupère une commande par sa référence externe en maintenant l'isolation multi-tenant.
    Garantit l'idempotence au sein d'un même tenant sans fuite d'informations entre tenants.
    """
    if not supabase_db or not external_reference or not tenant_id:
        return None
    try:
        query = (
            supabase_db.table("orders")
            .select("*")
            .eq("external_reference", external_reference)
            .eq("tenant_id", tenant_id)
        )
        res = query.execute()
        if res and hasattr(res, "data") and isinstance(res.data, list) and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération de la commande par référence externe : {e}")
        return None


def create_order_with_items(order_data: dict, items: list) -> dict:
    """
    Crée une commande canonique dans `orders` et insère ses lignes `order_items`.
    Incorpore le contrôle des options du tenant, le recalcul du prix via la DB,
    et la structure JSONB dans `details`.
    """
    if not supabase_db or not order_data:
        return {"success": False, "error": "Base de données indisponible"}

    tenant_id = order_data.get("tenant_id")
    delivery_type = order_data.get("delivery_type", "pickup")

    try:
        # 1. Vérification des fonctionnalités activées pour le Tenant
        if tenant_id:
            tenant_res = supabase_db.table("tenants").select("delivery_enabled, pickup_enabled").eq("id", tenant_id).execute()
            if tenant_res and hasattr(tenant_res, "data") and tenant_res.data:
                tenant_settings = tenant_res.data[0]
                if delivery_type == "delivery" and tenant_settings.get("delivery_enabled") is False:
                    return {"success": False, "error": "Livraison désactivée pour ce tenant"}
                if delivery_type == "pickup" and tenant_settings.get("pickup_enabled") is False:
                    return {"success": False, "error": "Retrait en magasin désactivé pour ce tenant"}

        # 2. Gestion de l'idempotence via external_reference (Isolé par tenant_id)
        ext_ref = order_data.get("external_reference")
        if ext_ref:
            existing = get_order_by_external_reference(ext_ref, tenant_id)
            if existing:
                logger.info(f"ℹ️ Commande {ext_ref} déjà existante pour le tenant {tenant_id} (Idempotence respectée).")
                res_obj = dict(existing)
                res_obj["success"] = True
                return res_obj

        # 3. Recalcul obligatoire des prix via les produits en BDD
        calculated_total = 0.0
        item_payloads = []
        details_items = []

        for item in items:
            prod_id = item["product_id"]
            qty = item.get("quantity", 1)

            # Récupération du prix canonique en DB
            prod_res = supabase_db.table("products").select("price").eq("id", prod_id).execute()
            if prod_res and hasattr(prod_res, "data") and prod_res.data and prod_res.data[0].get("price") is not None:
                real_price = float(prod_res.data[0]["price"])
            else:
                real_price = float(item.get("price") or item.get("unit_price") or 0.0)

            calculated_total += real_price * qty

            item_payloads.append({
                "product_id": prod_id,
                "quantity": qty,
                "unit_price": real_price
            })

            details_items.append({
                "product_id": prod_id,
                "quantity": qty,
                "price": real_price
            })

        # 4. Construction et mise à jour du payload de la commande
        order_payload = dict(order_data)
        order_payload["total_amount"] = calculated_total

        # Structure canonique de la colonne JSONB 'details'
        current_details = order_payload.get("details") if isinstance(order_payload.get("details"), dict) else {}
        current_details["items"] = details_items
        current_details["delivery_type"] = delivery_type
        if "delivery_address" in order_payload:
            current_details["delivery_address"] = order_payload["delivery_address"]
        order_payload["details"] = current_details

        # 5. Insertion dans la table 'orders'
        res = supabase_db.table("orders").insert(order_payload).execute()
        if not res or not hasattr(res, "data") or not res.data:
            return {"success": False, "error": "Échec d'insertion de la commande"}

        order = res.data[0]
        order_id = order["id"]

        # 6. Insertion dans la table 'order_items'
        for payload in item_payloads:
            payload["order_id"] = order_id

        if item_payloads:
            supabase_db.table("order_items").insert(item_payloads).execute()

        order["success"] = True
        order["order_id"] = order_id
        return order

    except Exception as e:
        logger.error(f"❌ Erreur lors de la création de la commande : {e}")
        return {"success": False, "error": str(e)}


def get_orders_by_tenant(tenant_id: str, status: str = None, limit: int = 50) -> list[dict]:
    """Récupère la liste des commandes d'un tenant avec les infos client et articles."""
    if not supabase_db:
        return []
    try:
        query = supabase_db.table("orders").select(
            "*, customers(full_name, phone), order_items(*, products(name, sku))"
        ).eq("tenant_id", tenant_id)

        if status:
            query = query.eq("status", status)

        response = query.order("created_at", desc=True).limit(limit).execute()
        return response.data if response and hasattr(response, "data") and response.data else []
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération des commandes Supabase : {e}")
        return []


def update_order_status_atomic(order_id: str, tenant_id: str, new_status: str) -> dict:
    """
    Met à jour le statut d'une commande de manière atomique avec isolation multi-tenant.
    Transmet systématiquement le tenant_id à la fonction RPC ou à la requête directe.
    """
    if not supabase_db or not order_id or not tenant_id:
        return {"success": False, "message": "Base de données indisponible ou paramètres invalides", "order": None}

    try:
        if new_status == "completed":
            # Transmission explicite de p_tenant_id pour parer aux failles BOLA au niveau du RPC
            rpc_res = supabase_db.rpc(
                "complete_order_and_decrement_stock", 
                {
                    "p_order_id": order_id,
                    "p_tenant_id": tenant_id
                }
            ).execute()

            if rpc_res and hasattr(rpc_res, "data") and rpc_res.data and rpc_res.data.get("success"):
                updated_order = (
                    supabase_db.table("orders")
                    .select("*")
                    .eq("id", order_id)
                    .eq("tenant_id", tenant_id)
                    .execute()
                )
                return {
                    "success": True, 
                    "message": rpc_res.data.get("message"),
                    "order": updated_order.data[0] if updated_order and hasattr(updated_order, "data") and updated_order.data else None
                }
            else:
                err_msg = rpc_res.data.get("message") if rpc_res and hasattr(rpc_res, "data") and rpc_res.data else "Commande introuvable ou non autorisée"
                return {"success": False, "message": err_msg, "order": None}
        else:
            # Appel positionnel strict pour éviter l'erreur de signature de fonction
            updated_order = update_order_status(order_id, new_status, tenant_id)
            if updated_order:
                return {
                    "success": True, 
                    "message": f"Statut mis à jour vers '{new_status}'",
                    "order": updated_order
                }
            return {"success": False, "message": "Commande introuvable ou non autorisée", "order": None}
    except Exception as e:
        logger.error(f"❌ Erreur lors de la mise à jour atomique du statut de la commande {order_id} : {e}")
        return {"success": False, "message": str(e), "order": None}


def update_order_status(order_id: str, new_status: str, tenant_id: str) -> dict:
    """
    Met à jour le statut d'une commande en imposing le contrôle par tenant_id,
    et renseigne les horodatages de complétion ou d'annulation.
    """
    if not supabase_db or not order_id or not tenant_id:
        return None
    try:
        # Vérification préalable sous condition d'appartenance au tenant
        curr = (
            supabase_db.table("orders")
            .select("*")
            .eq("id", order_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )

        if not curr or not hasattr(curr, "data") or not curr.data:
            return None

        now_iso = datetime.now(timezone.utc).isoformat()
        update_payload = {"status": new_status, "updated_at": now_iso}

        if new_status == "completed":
            update_payload["completed_at"] = now_iso
        elif new_status == "cancelled":
            update_payload["cancelled_at"] = now_iso

        res = (
            supabase_db.table("orders")
            .update(update_payload)
            .eq("id", order_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )
        return res.data[0] if res and hasattr(res, "data") and res.data else None
    except Exception as e:
        logger.error(f"❌ Erreur lors du changement de statut de commande : {e}")
        return None


# ==========================================
# GESTION DU MODE DE CONVERSATION (BOT / HUMAN)
# ==========================================

def get_conversation_mode(whatsapp_phone_number_id, customer_phone):
    if not supabase_db:
        return "bot"
    try:
        tenant_id = _get_tenant_id(whatsapp_phone_number_id)
        if not tenant_id:
            return "bot"
        customer_id = _get_or_create_customer(tenant_id, customer_phone)
        if not customer_id:
            return "bot"

        res = supabase_db.table("conversations") \
            .select("status") \
            .eq("tenant_id", tenant_id) \
            .eq("customer_id", customer_id) \
            .execute()

        if res and hasattr(res, "data") and res.data:
            return "human" if res.data[0]["status"] == "handover" else "bot"
        return "bot"
    except Exception as e:
        logger.error(f"❌ Erreur lors de la lecture du mode de conversation : {e}")
        return "bot"


def set_conversation_mode(whatsapp_phone_number_id, customer_phone, mode):
    if not supabase_db or mode not in ("bot", "human"):
        return False
    try:
        tenant_id = _get_tenant_id(whatsapp_phone_number_id)
        if not tenant_id:
            return False
        customer_id = _get_or_create_customer(tenant_id, customer_phone)
        if not customer_id:
            return False

        status_value = "handover" if mode == "human" else "active"

        supabase_db.table("conversations").upsert(
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "status": status_value,
                "last_interaction_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="tenant_id,customer_id",
        ).execute()
        return True
    except Exception as e:
        logger.error(f"❌ Erreur lors du changement de mode de conversation : {e}")
        return False


def get_human_mode_conversations(whatsapp_phone_number_id):
    if not supabase_db:
        return []
    try:
        tenant_id = _get_tenant_id(whatsapp_phone_number_id)
        if not tenant_id:
            return []

        res = supabase_db.table("conversations") \
            .select("customers(phone)") \
            .eq("tenant_id", tenant_id) \
            .eq("status", "handover") \
            .execute()

        if not res or not hasattr(res, "data") or not res.data:
            return []

        return [row["customers"]["phone"] for row in res.data if row.get("customers")]
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération des conversations en mode humain : {e}")
        return []


# ==========================================
# DASHBOARD (LECTURE SEULE)
# ==========================================

def get_cart_funnel_stats(whatsapp_phone_number_id):
    empty = {"pending": 0, "reminder_1_sent": 0, "reminder_2_sent": 0, "expired": 0, "completed": 0}
    if not supabase_db:
        return empty
    try:
        tenant_id = _get_tenant_id(whatsapp_phone_number_id)
        if not tenant_id:
            return empty

        res = supabase_db.table("carts") \
            .select("status") \
            .eq("tenant_id", tenant_id) \
            .execute()

        if not res or not hasattr(res, "data") or not res.data:
            return empty

        counts = dict(empty)
        for row in res.data:
            status = row.get("status", "pending")
            counts[status] = counts.get(status, 0) + 1
        return counts
    except Exception as e:
        logger.error(f"❌ Erreur lors du calcul des statistiques de panier : {e}")
        return empty


def get_recent_conversations(whatsapp_phone_number_id, limit=20):
    """Optimisé pour effectuer 1 seule requête SQL récurrente avec jointure PostgREST."""
    if not supabase_db:
        return []
    try:
        tenant_id = _get_tenant_id(whatsapp_phone_number_id)
        if not tenant_id:
            return []

        res = supabase_db.table("conversations") \
            .select("id, status, last_interaction_at, customers(phone), messages(content, sender_type, created_at)") \
            .eq("tenant_id", tenant_id) \
            .order("last_interaction_at", desc=True) \
            .order("created_at", foreign_table="messages", desc=True) \
            .limit(limit) \
            .execute()

        if not res or not hasattr(res, "data") or not res.data:
            return []

        result = []
        for conv in res.data:
            customer_phone = conv.get("customers", {}).get("phone")
            if not customer_phone:
                continue

            messages = conv.get("messages", [])
            last_msg = messages[0] if messages else {}

            result.append({
                "customer_phone": customer_phone,
                "last_message": last_msg.get("content", ""),
                "last_role": "user" if last_msg.get("sender_type") == "user" else "assistant",
                "last_at": conv.get("last_interaction_at"),
                "mode": "human" if conv.get("status") == "handover" else "bot"
            })

        return result
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération des conversations récentes : {e}")
        return []