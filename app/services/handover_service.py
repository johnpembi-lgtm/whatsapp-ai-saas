"""
Centralise toute la logique BOT_MODE / HUMAN_MODE : détection du besoin de
transfert, activation/désactivation, notification du vendeur.
"""
import logging
from app.core import database
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)

TRANSFER_KEYWORDS = [
    "parler à quelqu'un", "parler a quelquun", "parler au responsable",
    "un humain", "un vrai vendeur", "service client",
    "négocier le prix", "negocier le prix", "négocier",
    "problème avec ma commande", "probleme avec ma commande",
    "ne comprend rien", "comprend rien", "réclamation", "reclamation",
]


def is_transfer_requested(user_text: str) -> bool:
    if not user_text:
        return False
    text_lower = user_text.lower()
    return any(kw in text_lower for kw in TRANSFER_KEYWORDS)


def get_mode(phone_number_id: str, customer_phone: str) -> str:
    return database.get_conversation_mode(phone_number_id, customer_phone) or "bot"


def activate_human_mode(
    phone_number_id: str,
    customer_phone: str,
    tenant: dict,
    access_token: str,
    trigger_message: str = ""
) -> bool:
    changed = database.set_conversation_mode(phone_number_id, customer_phone, "human")
    if not changed:
        return False

    vendor_phone = tenant.get("vendor_phone") if tenant else None
    if vendor_phone:
        # Nettoyage du numéro pour éviter l'affichage "++"
        clean_customer_phone = str(customer_phone).lstrip("+")
        
        notif = (
            f"🔔 *Nouveau transfert client*\n\n"
            f"👤 Client : +{clean_customer_phone}\n"
            f"💬 \"{trigger_message}\"\n\n"
            f"👉 Répondez avec : /envoyer {clean_customer_phone} <message>\n"
            f"Ou tapez /reprendre {clean_customer_phone} pour rendre la main à l'IA."
        )
        try:
            WhatsAppService.send_message(
                phone_number_id=phone_number_id,
                recipient_phone=vendor_phone,
                message_text=notif,
                access_token=access_token,
            )
        except Exception as e:
            logger.error(f"Échec de l'envoi de la notification WhatsApp au vendeur ({vendor_phone}) : {e}")

    return True


def deactivate_human_mode(phone_number_id: str, customer_phone: str) -> bool:
    return database.set_conversation_mode(phone_number_id, customer_phone, "bot")


def get_active_human_conversations(phone_number_id: str) -> list:
    conversations = database.get_human_mode_conversations(phone_number_id)
    return conversations if conversations is not None else []