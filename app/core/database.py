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

# Le client backend/admin principal utilise STRICTEMENT la service_role_key pour contourner RLS
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

def _get_tenant_id(whatsapp_phone_number_id: str) -> str:
    """Récupère l'UUID du tenant à partir de son whatsapp_phone_number_id."""
    if not supabase_db or not whatsapp_phone_number_id:
        return None
    try:
        res = supabase_db.table("tenants") \
            .select("id") \
            .eq("whatsapp_phone_number_id", str(whatsapp_phone_number_id).strip()) \
            .execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération du tenant_id : {e}")
    return None


def _get_or_create_customer(tenant_id: str, phone: str) -> str:
    """Récupère ou crée le client (table `customers`, colonne `phone`)."""
    if not supabase_db or not tenant_id or not phone:
        return None
    clean_phone = str(phone).strip().replace("+", "").replace(" ", "")
    try:
        res = supabase_db.table("customers") \
            .select("id") \
            .eq("tenant_id", tenant_id) \
            .eq("phone", clean_phone) \
            .execute()
        if res.data:
            return res.data[0]["id"]

        # Création canonique
        ins = supabase_db.table("customers").insert({
            "tenant_id": tenant_id,
            "phone": clean_phone,
            "full_name": clean_phone
        }).execute()
        if ins.data:
            return ins.data[0]["id"]
    except Exception as e:
        logger.error(f"❌ Erreur lors de la résolution du customer_id : {e}")
    return None


def _get_or_create_conversation(tenant_id: str, customer_id: str) -> str:
    """Récupère ou crée la conversation canonique pour un couple (tenant, customer)."""
    if not supabase_db or not tenant_id or not customer_id:
        return None
    try:
        res = supabase_db.table("conversations") \
            .select("id") \
            .eq("tenant_id", tenant_id) \
            .eq("customer_id", customer_id) \
            .execute()
        if res.data:
            return res.data[0]["id"]

        ins = supabase_db.table("conversations").insert({
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "status": "active"
        }).execute()
        if ins.data:
            return ins.data[0]["id"]
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
# GESTION DU SUIVI DES PANIERS CANONIQUES
# ==========================================

def update_cart_tracking(whatsapp_phone_number_id, customer_phone, last_product=None, status='pending'):
    """Met à jour ou insère l'état du panier d'un client."""
    if not supabase_db:
        return
    try:
        tenant_id = _get_tenant_id(whatsapp_phone_number_id)
        if not tenant_id:
            return
        customer_id = _get_or_create_customer(tenant_id, customer_phone)
        if not customer_id:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "status": status,
            "last_interaction": now_iso,
            "updated_at": now_iso
        }

        supabase_db.table("carts").upsert(
            payload,
            on_conflict="tenant_id,customer_id"
        ).execute()

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

        if res.data:
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

        counts = dict(empty)
        for row in res.data:
            status = row.get("status", "pending")
            counts[status] = counts.get(status, 0) + 1
        return counts
    except Exception as e:
        logger.error(f"❌ Erreur lors du calcul des statistiques de panier : {e}")
        return empty


def get_recent_conversations(whatsapp_phone_number_id, limit=20):
    if not supabase_db:
        return []
    try:
        tenant_id = _get_tenant_id(whatsapp_phone_number_id)
        if not tenant_id:
            return []

        res = supabase_db.table("conversations") \
            .select("id, status, last_interaction_at, customers(phone)") \
            .eq("tenant_id", tenant_id) \
            .order("last_interaction_at", desc=True) \
            .limit(limit) \
            .execute()

        result = []
        for conv in res.data:
            customer_phone = conv.get("customers", {}).get("phone")
            if not customer_phone:
                continue

            msg_res = supabase_db.table("messages") \
                .select("content, sender_type, created_at") \
                .eq("conversation_id", conv["id"]) \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()

            last_msg = msg_res.data[0] if msg_res.data else {}

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