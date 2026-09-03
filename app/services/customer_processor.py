"""
Traite tous les messages provenant d'un CLIENT (pas le vendeur). Respecte
strictement BOT_MODE / HUMAN_MODE : en HUMAN_MODE, l'IA n'est jamais appelée
(voir doc Phase 2, section 4 — "la règle la plus importante de toute la phase").
"""
import re
import logging

from app.core import database
from app.services import handover_service
from app.services.ai_service import AIService
from app.services.whatsapp_service import WhatsAppService
from app.services.orders_service import OrdersService
from app.services.cart_service import CartService
from app.services.sheets_service import SheetsService

logger = logging.getLogger(__name__)


def _extract_text_and_location(msg_type: str, message_data: dict) -> tuple[str, dict]:
    """
    Extrait le texte d'un message WhatsApp et/ou les métadonnées de géolocalisation structurées.
    Retourne un tuple: (user_text, location_metadata)
    """
    if msg_type == "text":
        return message_data.get("text", {}).get("body", ""), None

    if msg_type == "location":
        loc = message_data.get("location", {})
        lat = loc.get("latitude")
        lng = loc.get("longitude")

        if lat is None or lng is None:
            return None, None

        name = loc.get("name", "").strip()
        address = loc.get("address", "").strip()

        details_parts = []
        if name:
            details_parts.append(name)
        if address:
            details_parts.append(address)

        details = " - ".join(details_parts)
        maps_url = f"https://maps.google.com/?q={lat},{lng}"

        user_text = (
            f"[LOCALISATION PARTAGÉE : Lat {lat}, Long {lng}"
            f"{f' ({details})' if details else ''} | "
            f"Google Maps: {maps_url}]"
        )

        location_data = {
            "latitude": float(lat),
            "longitude": float(lng),
            "name": name or None,
            "address": address or None,
            "google_maps_url": maps_url
        }

        return user_text, location_data

    return None, None


def handle_customer_message(tenant, phone_number_id, sender_phone, message_data, access_token):
    msg_type = message_data.get("type")
    user_text, location_data = _extract_text_and_location(msg_type, message_data)

    if user_text is None:
        return  # Type de message non géré côté client (audio, sticker, etc.)

    # Récupère l'historique AVANT d'enregistrer le message courant
    history = database.get_conversation_history(phone_number_id, sender_phone, limit=6)

    # Historique conservé même en HUMAN_MODE pour le contexte vendeur
    database.save_message(phone_number_id, sender_phone, "user", user_text)

    # --- RÈGLE D'OR : en HUMAN_MODE, l'IA ne doit JAMAIS être appelée ---
    mode = handover_service.get_mode(phone_number_id, sender_phone)
    if mode == "human":
        logger.info(f"🤫 Conversation {sender_phone} en HUMAN_MODE — IA non sollicitée.")
        return

    # --- Détection d'une demande explicite de transfert ---
    if handover_service.is_transfer_requested(user_text):
        handover_service.activate_human_mode(
            phone_number_id, sender_phone, tenant, access_token, trigger_message=user_text
        )
        WhatsAppService.send_message(
            phone_number_id=phone_number_id,
            recipient_phone=sender_phone,
            message_text="Je transmets votre demande à notre équipe, elle vous répond très vite ! 🙏",
            access_token=access_token,
        )
        database.save_message(
            phone_number_id,
            sender_phone,
            "assistant",
            "Je transmets votre demande à notre équipe, elle vous répond très vite ! 🙏"
        )
        return

    # --- Traitement IA classique & Suivi Panier ---
    CartService.update_interaction(phone_number_id, sender_phone)
    catalog = SheetsService.fetch_catalog(tenant.get("sheets_id"))

    ai_reply = AIService.generate_response(
        tenant.get("system_prompt"), catalog, user_text, history=history,
    )
    logger.info(f"🤖 Réponse IA générée pour [{sender_phone}] : {ai_reply}")

    image_match = re.search(r"\[SEND_IMAGE:\s*(https?://[^\s\]]+)\]", ai_reply)
    if image_match:
        image_url = image_match.group(1)
        clean_reply = re.sub(r"\[SEND_IMAGE:\s*https?://[^\s\]]+\]", "", ai_reply).strip()
        sent = WhatsAppService.send_image(
            phone_number_id=phone_number_id,
            recipient_phone=sender_phone,
            image_url=image_url,
            caption_text=clean_reply,
            access_token=access_token,
        )
        if not sent and clean_reply:
            WhatsAppService.send_message(
                phone_number_id=phone_number_id,
                recipient_phone=sender_phone,
                message_text=clean_reply,
                access_token=access_token,
            )
        stored_reply = clean_reply or "Image du produit envoyée."
    else:
        clean_reply = ai_reply
        WhatsAppService.send_message(
            phone_number_id=phone_number_id,
            recipient_phone=sender_phone,
            message_text=clean_reply,
            access_token=access_token,
        )
        stored_reply = clean_reply

    database.save_message(phone_number_id, sender_phone, "assistant", stored_reply)

    OrdersService.record_order_if_completed(
        tenant=tenant,
        phone_number_id=phone_number_id,
        sender_phone=sender_phone,
        history=history,
        user_text=user_text,
        ai_reply=ai_reply,
        location_data=location_data
    )