"""
Traite tous les messages provenant d'un CLIENT (pas le vendeur). Respecte
strictement BOT_MODE / HUMAN_MODE : en HUMAN_MODE, l'IA n'est jamais appelée
(voir doc Phase 2, section 4 — "la règle la plus importante de toute la phase").
"""
import re

from app.core import database
from app.services import handover_service
from app.services.ai_service import AIService
from app.services.whatsapp_service import WhatsAppService
from app.services.orders_service import OrdersService
from app.services.cart_service import CartService
from app.services.sheets_service import SheetsService


def _extract_text(msg_type, message_data):
    if msg_type == "text":
        return message_data.get("text", {}).get("body", "")

    if msg_type == "location":
        loc = message_data.get("location", {})
        lat, lng = loc.get("latitude"), loc.get("longitude")
        if not (lat and lng):
            return None
        name = loc.get("name", "")
        address = loc.get("address", "")
        details = f" ({name} - {address})".strip(" ()")
        return (
            f"[LOCALISATION PARTAGÉE : Lat {lat}, Long {lng}"
            f"{f' - {details}' if details else ''} | "
            f"Google Maps: https://maps.google.com/?q={lat},{lng}]"
        )

    return None


def handle_customer_message(tenant, phone_number_id, sender_phone, message_data, access_token):
    msg_type = message_data.get("type")
    user_text = _extract_text(msg_type, message_data)

    if user_text is None:
        return  # Type de message non géré côté client (audio, sticker...)

    # Récupère l'historique AVANT d'enregistrer le message courant afin de ne
    # pas injecter deux fois le même message utilisateur dans le prompt IA.
    history = database.get_conversation_history(phone_number_id, sender_phone, limit=6)

    # Historique conservé même en HUMAN_MODE, pour que le vendeur ait le contexte complet.
    database.save_message(phone_number_id, sender_phone, "user", user_text)

    # --- RÈGLE D'OR : en HUMAN_MODE, l'IA ne doit JAMAIS être appelée ---
    mode = handover_service.get_mode(phone_number_id, sender_phone)
    if mode == "human":
        print(f"🤫 Conversation {sender_phone} en HUMAN_MODE — IA non sollicitée.")
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
        database.save_message(phone_number_id, sender_phone, "assistant",
                               "Je transmets votre demande à notre équipe, elle vous répond très vite ! 🙏")
        return

    # --- Traitement IA classique ---
    CartService.update_interaction(phone_number_id, sender_phone)
    catalog = SheetsService.fetch_catalog(tenant.get("sheets_id"))

    ai_reply = AIService.generate_response(
        tenant.get("system_prompt"), catalog, user_text, history=history,
    )
    print(f"🤖 Réponse IA générée pour [{sender_phone}] : {ai_reply}")

    image_match = re.search(r"\[SEND_IMAGE:\s*(https?://[^\s\]]+)\]", ai_reply)
    if image_match:
        image_url = image_match.group(1)
        clean_reply = re.sub(r"\[SEND_IMAGE:\s*https?://[^\s\]]+\]", "", ai_reply).strip()
        sent = WhatsAppService.send_image(
            phone_number_id=phone_number_id, recipient_phone=sender_phone,
            image_url=image_url, caption_text=clean_reply, access_token=access_token,
        )
        # Si l'image échoue, le client reçoit tout de même le texte utile.
        if not sent and clean_reply:
            WhatsAppService.send_message(
                phone_number_id=phone_number_id, recipient_phone=sender_phone,
                message_text=clean_reply, access_token=access_token,
            )
        stored_reply = clean_reply or "Image du produit envoyée."
    else:
        clean_reply = ai_reply
        WhatsAppService.send_message(
            phone_number_id=phone_number_id, recipient_phone=sender_phone,
            message_text=clean_reply, access_token=access_token,
        )
        stored_reply = clean_reply

    # Ne stocke pas le tag technique SEND_IMAGE dans l'historique visible.
    database.save_message(phone_number_id, sender_phone, "assistant", stored_reply)

    OrdersService.record_order_if_completed(
        tenant=tenant, phone_number_id=phone_number_id, sender_phone=sender_phone,
        history=history, user_text=user_text, ai_reply=ai_reply,
    )