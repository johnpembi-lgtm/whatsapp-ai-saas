import hmac
import hashlib
import logging
from flask import request
from flask import current_app

logger = logging.getLogger(__name__)

def verify_meta_signature(app_secret: str) -> bool:
    """
    Vérifie la signature X-Hub-Signature-256 transmise par Meta.
    Retourne True si la signature est valide, False sinon.
    """
    signature_header = request.headers.get("X-Hub-Signature-256")
    
    if not signature_header:
        logger.warning("Sécurité Webhook : Header X-Hub-Signature-256 manquant.")
        return False

    elements = signature_header.split("=")
    if len(elements) != 2 or elements[0] != "sha256":
        logger.warning("Sécurité Webhook : Format de signature invalide.")
        return False

    expected_hash = elements[1]
    raw_payload = request.get_data()

    # Calcul du HMAC SHA256 avec la clé secrète de l'application
    actual_hash = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=raw_payload,
        digestmod=hashlib.sha256
    ).hexdigest()

    # Comparaison sécurisée contre les attaques par analyse temporelle (timing attacks)
    is_valid = hmac.compare_digest(actual_hash, expected_hash)
    if not is_valid:
        logger.error("Sécurité Webhook : Signature non valide ! Requête falsifiée rejetée.")
    
    return is_valid