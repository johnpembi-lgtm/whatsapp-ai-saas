import os
import time
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
    """Gère la configuration multi-tenant des boutiques clientes via Supabase (avec Cache TTL 5 min)."""

    # Cache mémoire : { whatsapp_phone_number_id: (timestamp, tenant_dict) }
    _tenant_cache = {}
    _TENANT_CACHE_TTL_SECONDS = 300  # 5 minutes

    @classmethod
    def invalidate_cache(cls, whatsapp_phone_number_id: str = None):
        """Invalide le cache pour un tenant spécifique ou purge l'intégralité du cache."""
        if whatsapp_phone_number_id:
            clean_id = str(whatsapp_phone_number_id).strip()
            cls._tenant_cache.pop(clean_id, None)
            logger.info(f"🔄 Cache tenant invalidé pour l'ID WhatsApp : {clean_id}")
        else:
            cls._tenant_cache.clear()
            logger.info("🔄 Tout le cache des tenants a été vidé.")

    @classmethod
    def get_tenants(cls):
        """Récupère toutes les boutiques indexées par whatsapp_phone_number_id."""
        if not supabase:
            return {}
        try:
            res = supabase.table("tenants").select("*").execute()
            tenants = {}
            for row in res.data:
                # Injection de clés d'alias pour la compatibilité avec le reste du projet
                row["tenant_id"] = row.get("id")
                row["store_id"] = row.get("name") or row.get("store_id")
                row["sheets_id"] = row.get("google_sheet_id") or row.get("sheets_id")

                phone_id = row.get("whatsapp_phone_number_id")
                if phone_id:
                    tenants[phone_id] = row
            return tenants
        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération des boutiques : {e}")
            return {}

    @classmethod
    def get_tenant_by_phone_id(cls, whatsapp_phone_number_id: str):
        """Récupère une boutique par son WhatsApp Phone Number ID Meta (avec cache mémoire TTL 5min)."""
        if not supabase or not whatsapp_phone_number_id:
            return None

        clean_phone_id = str(whatsapp_phone_number_id).strip()

        # 1. Vérification du cache mémoire
        cached = cls._tenant_cache.get(clean_phone_id)
        if cached:
            timestamp, tenant_data = cached
            if (time.time() - timestamp) < cls._TENANT_CACHE_TTL_SECONDS:
                return tenant_data

        # 2. Requête Supabase si absente du cache ou expirée
        try:
            res = (
                supabase.table("tenants")
                .select("*")
                .eq("whatsapp_phone_number_id", clean_phone_id)
                .execute()
            )

            if not res.data:
                logger.warning(f"❌ Aucune boutique configurée pour l'ID WhatsApp : {clean_phone_id}")
                return None

            tenant = res.data[0]

            # Vérification de l'état actif
            is_active = tenant.get("status") == "active" if "status" in tenant else tenant.get("is_active", True)
            if not is_active:
                logger.warning(f"⚠️ La boutique [{tenant.get('name') or tenant.get('store_name')}] est désactivée.")
                return None

            # Injection des clés alias pour la compatibilité du reste de l'application
            tenant["tenant_id"] = tenant.get("id")
            tenant["store_id"] = tenant.get("name") or tenant.get("store_id")
            tenant["sheets_id"] = tenant.get("google_sheet_id") or tenant.get("sheets_id")

            # 3. Mise en cache
            cls._tenant_cache[clean_phone_id] = (time.time(), tenant)
            return tenant

        except Exception as e:
            logger.error(f"❌ Erreur lors de la recherche du tenant {clean_phone_id} : {e}")
            return None

    @classmethod
    def add_or_update_tenant(
        cls,
        phone_number_id: str = None,
        whatsapp_phone_number_id: str = None,
        store_id: str = None,
        name: str = None,
        vendor_phone: str = None,
        sheets_id: str = None,
        google_sheet_id: str = None,
        whatsapp_access_token: str = None,
        system_prompt: str = "",
        status: str = "active",
        vendor_email: str = None,
        ai_config: dict = None,
        **kwargs,
    ):
        """Ajoute ou met à jour une boutique dans Supabase et invalide son cache.
        Accepte les alias de paramètres pour rétrocompatibilité (phone_number_id/whatsapp_phone_number_id, store_id/name, sheets_id/google_sheet_id).
        """
        if not supabase:
            return False

        # Résolution flexible des arguments
        final_phone_id = (phone_number_id or whatsapp_phone_number_id or "").strip()
        final_name = (store_id or name or "").strip()
        final_sheet_id = (sheets_id or google_sheet_id or "").strip()

        if not final_phone_id or not final_name:
            logger.error("❌ Impossible de sauvegarder le tenant : ID WhatsApp ou Nom de boutique manquant.")
            return False

        clean_vendor = None
        if vendor_phone:
            clean_vendor = str(vendor_phone).strip().replace("+", "").replace(" ", "")

        default_prompt = (
            system_prompt.strip()
            or f"Tu es l'assistant commercial virtuel de la boutique {final_name}. "
               f"Sois poli, efficace, et aide les clients à trouver des produits et passer commande."
        )

        config_payload = ai_config if ai_config is not None else {}
        if system_prompt:
            config_payload["system_prompt"] = default_prompt

        payload = {
            "whatsapp_phone_number_id": final_phone_id,
            "name": final_name,
            "status": status,
            "system_prompt": default_prompt,
            "ai_config": config_payload,
            "updated_at": "now()",
        }

        if clean_vendor:
            payload["vendor_phone"] = clean_vendor
        if final_sheet_id:
            payload["google_sheet_id"] = final_sheet_id
        if whatsapp_access_token:
            payload["whatsapp_access_token"] = whatsapp_access_token.strip()
        if vendor_email and vendor_email.strip():
            payload["vendor_email"] = vendor_email.strip()

        try:
            res = (
                supabase.table("tenants")
                .upsert(payload, on_conflict="whatsapp_phone_number_id")
                .execute()
            )
            if res.data:
                # Invalidation automatique du cache après mise à jour
                cls.invalidate_cache(final_phone_id)
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'upsert de la boutique {final_name} : {e}")
            return False