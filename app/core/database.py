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