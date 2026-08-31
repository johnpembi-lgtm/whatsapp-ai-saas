import os
import logging
from typing import Tuple, Optional
from supabase import create_client, Client

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").split("/rest/v1")[0].rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    logger.warning("⚠️ Supabase non configuré dans deduplicator.py")


class PersistentDeduplicator:
    """Gère l'idempotence des webhooks Meta via Supabase (table webhook_events)."""

    @classmethod
    def register_and_check(cls, message_id: str, tenant_id: str, event_type: str = "message") -> Tuple[bool, str]:
        """
        Tente d'enregistrer atomiquement un message.
        
        Returns:
            (is_duplicate, status)
            - (False, "new") : Premier passage, enregistrement créé avec status="processing".
            - (True, "already_processed") : Déjà traité avec succès.
            - (True, "in_progress") : En cours de traitement par un autre thread/process.
        """
        if not supabase or not message_id:
            return False, "new"

        clean_msg_id = str(message_id).strip()

        # 1. Tentative d'insertion atomique (Lock au niveau de la DB)
        try:
            res = supabase.table("webhook_events").insert({
                "tenant_id": tenant_id,
                "message_id": clean_msg_id,
                "event_type": event_type,
                "status": "processing"
            }).execute()

            if res.data:
                logger.info(f"🔒 [DEDUPLICATOR] Lock 'processing' posé pour message_id={clean_msg_id} (Tenant={tenant_id})")
                return False, "new"

        except Exception as e:
            err_str = str(e).lower()
            if "duplicate key" in err_str or "23505" in err_str:
                logger.warning(f"🔄 [DEDUPLICATOR] Doublon détecté pour message_id={clean_msg_id}")
            else:
                logger.error(f"⚠️ [DEDUPLICATOR] Erreur de vérification DB : {e}")

        # 2. Si l'insertion échoue, vérification du statut actuel
        try:
            existing = supabase.table("webhook_events").select("status").eq("message_id", clean_msg_id).execute()
            if existing.data:
                current_status = existing.data[0].get("status")
                if current_status == "processed":
                    return True, "already_processed"
                return True, "in_progress"
        except Exception as e:
            logger.error(f"❌ [DEDUPLICATOR] Erreur de lecture du statut : {e}")

        return True, "in_progress"

    @classmethod
    def mark_processed(cls, message_id: str):
        """Passe le statut du message à 'processed' après succès du traitement."""
        if not supabase or not message_id:
            return
        try:
            supabase.table("webhook_events").update({
                "status": "processed",
                "processed_at": "now()"
            }).eq("message_id", str(message_id).strip()).execute()
            logger.info(f"✅ [DEDUPLICATOR] Message {message_id} marqué comme 'processed'")
        except Exception as e:
            logger.error(f"❌ [DEDUPLICATOR] Échec de la mise à jour 'processed' : {e}")

    @classmethod
    def mark_failed(cls, message_id: str, error_msg: str):
        """Passe le statut à 'failed' et enregistre le message d'erreur."""
        if not supabase or not message_id:
            return
        try:
            supabase.table("webhook_events").update({
                "status": "failed",
                "error": str(error_msg)[:500]
            }).eq("message_id", str(message_id).strip()).execute()
            logger.error(f"❌ [DEDUPLICATOR] Message {message_id} marqué comme 'failed' : {error_msg}")
        except Exception as e:
            logger.error(f"❌ [DEDUPLICATOR] Échec de la mise à jour 'failed' : {e}")