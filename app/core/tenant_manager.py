import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logger = logging.getLogger(__name__)

raw_url = os.getenv("SUPABASE_URL", "")
SUPABASE_URL = raw_url.split("/rest/v1")[0].rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    logger.warning("⚠️ Supabase non configuré dans tenant_manager.py")


class TenantManager:
    """Gère la configuration multi-tenant des boutiques clientes via Supabase."""

    @classmethod
    def get_tenants(cls):
        """Récupère toutes les boutiques indexées par phone_number_id."""
        if not supabase:
            return {}
        try:
            res = supabase.table("tenants").select("*").execute()
            tenants = {}
            for row in res.data:
                # Injection de la clé tenant_id explicite
                row["tenant_id"] = row.get("id")
                tenants[row["phone_number_id"]] = row
            return tenants
        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération des boutiques : {e}")
            return {}

    @classmethod
    def get_tenant_by_phone_id(cls, phone_number_id):
        """Récupère une boutique par son Phone Number ID Meta."""
        if not supabase:
            return None
        clean_phone_id = str(phone_number_id).strip()
        try:
            res = supabase.table("tenants").select("*").eq("phone_number_id", clean_phone_id).execute()
            if not res.data:
                logger.warning(f"❌ Aucune boutique configurée pour l'ID : {clean_phone_id}")
                return None

            tenant = res.data[0]
            if not tenant.get("is_active", True):
                logger.warning(f"⚠️ La boutique [{tenant.get('store_name')}] est désactivée.")
                return None

            # S'assurer que le tenant possède son UUID interne
            tenant["tenant_id"] = tenant.get("id")
            return tenant
        except Exception as e:
            logger.error(f"❌ Erreur lors de la recherche du tenant {clean_phone_id} : {e}")
            return None

    @classmethod
    def add_or_update_tenant(
        cls,
        phone_number_id,
        store_id,
        vendor_phone,
        sheets_id,
        system_prompt="",
        is_active=True,
        vendor_email="",
    ):
        """Ajoute ou met à jour une boutique dans Supabase."""
        if not supabase:
            return False
        clean_phone_id = str(phone_number_id).strip()
        clean_vendor = str(vendor_phone).strip().replace("+", "").replace(" ", "")
        clean_store = store_id.strip()
        default_prompt = (
            system_prompt.strip()
            or f"Tu es l'assistant commercial virtuel de la boutique {clean_store}. "
               f"Sois poli, efficace, et aide les clients à trouver des produits et passer commande."
        )

        payload = {
            "phone_number_id": clean_phone_id,
            "store_id": clean_store,
            "store_name": clean_store,
            "vendor_phone": clean_vendor,
            "sheets_id": sheets_id.strip(),
            "system_prompt": default_prompt,
            "is_active": is_active,
        }
        if vendor_email and vendor_email.strip():
            payload["vendor_email"] = vendor_email.strip()

        try:
            res = supabase.table("tenants").upsert(payload, on_conflict="phone_number_id").execute()
            return bool(res.data)
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'upsert de la boutique {clean_store} : {e}")
            return False