"""
Centralise toute la logique BOT_MODE / HUMAN_MODE : détection du besoin de
transfert, activation/désactivation, notification du vendeur. Les routes et
les autres services ne touchent jamais directement conversation_state dans
database.py — ils passent par ici.
"""
from app.core import database
from app.services.whatsapp_service import WhatsAppService


# Mots-clés déclenchant un transfert humain. Volontairement simple (pas de
# classification IA) pour rester prévisible en V1 — voir doc Phase 2, point 2 :
# ne PAS transférer pour chaque question mal comprise, seulement pour des
# signaux clairs et volontaires du client.
TRANSFER_KEYWORDS = [
    "parler à quelqu'un", "parler a quelquun", "parler au responsable",
    "un humain", "un vrai vendeur", "service client",
    "négocier le prix", "negocier le prix", "négocier",
    "problème avec ma commande", "probleme avec ma commande",
    "ne comprend rien", "comprend rien", "réclamation", "reclamation",
]


def is_transfer_requested(user_text):
    """Détecte si le message du client contient un signal explicite de
    demande de transfert humain."""
    text_lower = user_text.lower()
    return any(kw in text_lower for kw in TRANSFER_KEYWORDS)


def get_mode(phone_number_id, customer_phone):
    """Retourne 'bot' ou 'human' pour cette conversation."""
    return database.get_conversation_mode(phone_number_id, customer_phone)


def activate_human_mode(phone_number_id, customer_phone, tenant, access_token, trigger_message=""):
    """Bascule la conversation en HUMAN_MODE et notifie le vendeur."""
    changed = database.set_conversation_mode(phone_number_id, customer_phone, "human")
    if not changed:
        return False

    vendor_phone = tenant.get("vendor_phone")
    if vendor_phone:
        notif = (
            f"🔔 *Nouveau transfert client*\n\n"
            f"👤 Client : +{customer_phone}\n"
            f"💬 \"{trigger_message}\"\n\n"
            f"👉 Répondez avec : /envoyer {customer_phone} <message>\n"
            f"Ou tapez /reprendre {customer_phone} pour rendre la main à l'IA."
        )
        WhatsAppService.send_message(
            phone_number_id=phone_number_id,
            recipient_phone=vendor_phone,
            message_text=notif,
            access_token=access_token,
        )
    return True


def deactivate_human_mode(phone_number_id, customer_phone):
    """Rend la main à l'IA pour cette conversation (/reprendre ou /close)."""
    return database.set_conversation_mode(phone_number_id, customer_phone, "bot")


def get_active_human_conversations(phone_number_id):
    """Liste des numéros clients actuellement en HUMAN_MODE pour cette boutique."""
    return database.get_human_mode_conversations(phone_number_id)