import socket
import threading
import logging
from datetime import datetime, timedelta, timezone
from app.core.database import supabase_db

logger = logging.getLogger(__name__)


def acquire_lock(job_name: str, lock_duration_seconds: int = 600) -> bool:
    """
    Tente d'acquérir un verrou distribué sur Supabase.
    Retourne True si le verrou a été obtenu, False sinon.
    """
    if not supabase_db:
        return False

    now = datetime.now(timezone.utc)
    locked_until = now + timedelta(seconds=lock_duration_seconds)
    worker_id = f"{socket.gethostname()}_{id(threading.current_thread())}"

    try:
        # 1. Vérifier si un verrou existe déjà pour ce job
        res = supabase_db.table("job_locks").select("*").eq("job_name", job_name).execute()

        if res.data:
            current_lock = res.data[0]
            # Formatage de la date d'expiration en UTC
            lock_expiration_str = current_lock["locked_until"].replace("Z", "+00:00")
            lock_expiration = datetime.fromisoformat(lock_expiration_str)

            # Si le verrou est encore valide, un autre worker est en train d'exécuter la tâche
            if now < lock_expiration:
                logger.info(f"🔒 Job '{job_name}' est déjà en cours d'exécution par un autre worker.")
                return False

            # Si le verrou a expiré, on le reprend
            supabase_db.table("job_locks").update({
                "locked_until": locked_until.isoformat(),
                "locked_by": worker_id
            }).eq("job_name", job_name).execute()
            return True
        else:
            # Premier lancement : insertion du verrou
            supabase_db.table("job_locks").insert({
                "job_name": job_name,
                "locked_until": locked_until.isoformat(),
                "locked_by": worker_id
            }).execute()
            return True

    except Exception as e:
        logger.error(f"❌ Erreur lors de l'obtention du verrou ({job_name}) : {e}")
        return False