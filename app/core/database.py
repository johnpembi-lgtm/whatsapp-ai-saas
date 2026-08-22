import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Charger les variables du fichier .env
load_dotenv()

# Nettoyage automatique de l'URL
raw_url = os.getenv("SUPABASE_URL", "")
SUPABASE_URL = raw_url.split("/rest/v1")[0].rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialisation du client Supabase
supabase_db: Client = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase_db = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠️ Supabase non configuré dans app/core/database.py")


def init_db():
    """
    Laissé pour compatibilité avec le démarrage de l'application.
    Les tables sont désormais gérées directement sur l'interface de Supabase.
    """
    pass


# ==========================================
# GESTION DES MESSAGES / HISTORIQUE
# ==========================================

def save_message(phone_number_id, user_phone, role, content):
    """Enregistre un message (du client ou de l'IA) sur Supabase."""
    if not supabase_db:
        return
    try:
        payload = {
            "phone_number_id": str(phone_number_id),
            "user_phone": str(user_phone),
            "role": role,
            "content": content
        }
        supabase_db.table("messages").insert(payload).execute()
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde du message sur Supabase : {e}")


def get_conversation_history(phone_number_id, user_phone, limit=6):
    """Récupère l'historique chronologique des conversations depuis Supabase."""
    if not supabase_db:
        return []
    try:
        res = supabase_db.table("messages") \
            .select("role, content") \
            .eq("phone_number_id", str(phone_number_id)) \
            .eq("user_phone", str(user_phone)) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        
        history = [{"role": row["role"], "content": row["content"]} for row in res.data]
        history.reverse()
        return history
    except Exception as e:
        print(f"❌ Erreur de récupération d'historique sur Supabase : {e}")
        return []


# ==========================================
# GESTION DU SUIVI DES PANIERS (RETARGETING)
# ==========================================

def update_cart_tracking(phone_number_id, customer_phone, last_product=None, status='pending'):
    """Met à jour ou insère l'état du panier d'un client (Upsert)."""
    if not supabase_db:
        return
    try:
        payload = {
            "phone_number_id": str(phone_number_id),
            "customer_phone": str(customer_phone),
            "status": status,
            "last_interaction": "now()"
        }
        if last_product:
            payload["last_product"] = last_product

        supabase_db.table("cart_tracking").upsert(
            payload, 
            on_conflict="phone_number_id,customer_phone"
        ).execute()
    except Exception as e:
        print(f"❌ Erreur lors de la mise à jour du panier sur Supabase : {e}")


def get_pending_carts_for_retry(limit=10):
    """Récupère les paniers en attente pour les relances automatiques."""
    if not supabase_db:
        return []
    try:
        res = supabase_db.table("cart_tracking") \
            .select("*") \
            .eq("status", "pending") \
            .limit(limit) \
            .execute()
        return res.data
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des paniers en attente : {e}")
        return []


# ==========================================
# GESTION DU MODE DE CONVERSATION (BOT_MODE / HUMAN_MODE)
# ==========================================

def get_conversation_mode(phone_number_id, customer_phone):
    """Retourne 'bot' ou 'human' pour cette conversation précise. 'bot' par défaut
    si aucune ligne n'existe encore (conversation jamais escaladée)."""
    if not supabase_db:
        return "bot"
    try:
        res = supabase_db.table("conversation_state") \
            .select("mode") \
            .eq("phone_number_id", str(phone_number_id)) \
            .eq("customer_phone", str(customer_phone)) \
            .execute()
        if res.data:
            return res.data[0]["mode"]
        return "bot"
    except Exception as e:
        print(f"❌ Erreur lors de la lecture du mode de conversation : {e}")
        return "bot"


def set_conversation_mode(phone_number_id, customer_phone, mode):
    """Bascule une conversation précise en 'bot' ou 'human'."""
    if not supabase_db:
        return False
    if mode not in ("bot", "human"):
        return False
    try:
        supabase_db.table("conversation_state").upsert(
            {
                "phone_number_id": str(phone_number_id),
                "customer_phone": str(customer_phone),
                "mode": mode,
                "updated_at": "now()",
            },
            on_conflict="phone_number_id,customer_phone",
        ).execute()
        return True
    except Exception as e:
        print(f"❌ Erreur lors du changement de mode de conversation : {e}")
        return False


def get_human_mode_conversations(phone_number_id):
    """Liste les numéros clients actuellement en HUMAN_MODE pour cette boutique."""
    if not supabase_db:
        return []
    try:
        res = supabase_db.table("conversation_state") \
            .select("customer_phone") \
            .eq("phone_number_id", str(phone_number_id)) \
            .eq("mode", "human") \
            .execute()
        return [row["customer_phone"] for row in res.data]
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des conversations en mode humain : {e}")
        return []


# ==========================================
# DASHBOARD (LECTURE SEULE — Phase 4)
# ==========================================

def get_cart_funnel_stats(phone_number_id):
    """Compte les paniers par statut, pour visualiser le funnel de relance
    (pending → reminder_1_sent → reminder_2_sent → expired → completed)."""
    empty = {"pending": 0, "reminder_1_sent": 0, "reminder_2_sent": 0, "expired": 0, "completed": 0}
    if not supabase_db:
        return empty
    try:
        res = supabase_db.table("cart_tracking") \
            .select("status") \
            .eq("phone_number_id", str(phone_number_id)) \
            .execute()
        counts = dict(empty)
        for row in res.data:
            status = row.get("status", "pending")
            counts[status] = counts.get(status, 0) + 1
        return counts
    except Exception as e:
        print(f"❌ Erreur lors du calcul des statistiques de panier : {e}")
        return empty


def get_recent_conversations(phone_number_id, limit=20):
    """Liste les clients ayant écrit récemment, avec leur dernier message,
    l'horodatage, et leur mode actuel (bot/human)."""
    if not supabase_db:
        return []
    try:
        # On lit un peu plus large que `limit` messages pour pouvoir dédupliquer
        # par client tout en gardant les `limit` conversations les plus récentes.
        res = supabase_db.table("messages") \
            .select("user_phone, role, content, created_at") \
            .eq("phone_number_id", str(phone_number_id)) \
            .order("created_at", desc=True) \
            .limit(limit * 8) \
            .execute()

        conversations = {}
        for row in res.data:
            phone = row["user_phone"]
            if phone not in conversations:
                conversations[phone] = {
                    "customer_phone": phone,
                    "last_message": row["content"],
                    "last_role": row["role"],
                    "last_at": row["created_at"],
                }
            if len(conversations) >= limit:
                break

        human_set = set(get_human_mode_conversations(phone_number_id))
        result = list(conversations.values())
        for c in result:
            c["mode"] = "human" if c["customer_phone"] in human_set else "bot"
        return result
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des conversations récentes : {e}")
        return []