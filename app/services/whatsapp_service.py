import os
import requests
from flask import current_app


class WhatsAppService:
    """Service d'envoi de messages et médias via Meta WhatsApp Cloud API."""

    @staticmethod
    def _resolve_token(access_token=None):
        """Récupère le premier token disponible de manière sécurisée."""
        if access_token and access_token.strip():
            return access_token.strip()

        try:
            token = current_app.config.get("WHATSAPP_ACCESS_TOKEN")
            if token and token.strip():
                return token.strip()
        except RuntimeError:
            # En dehors du contexte de l'application Flask (threads de fond)
            pass

        return os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()

    @staticmethod
    def _get_headers(access_token=None):
        token = WhatsAppService._resolve_token(access_token)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def send_message(phone_number_id, recipient_phone, message_text, access_token=None):
        """Envoie un message texte simple."""
        token = WhatsAppService._resolve_token(access_token)
        
        # Log de débogage pour vérifier la validité
        masked_token = f"{token[:10]}...{token[-5:]}" if len(token) > 15 else "INVALIDE/VIDE"
        print(f"🔍 DEBUG ENVOI TEXTE | PhoneID: {phone_number_id} | Token: {masked_token}")

        url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "text",
            "text": {"body": message_text},
        }

        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            if response.status_code != 200:
                print(
                    f"❌ Erreur envoi WhatsApp Texte ({response.status_code}):"
                    f" {response.text}"
                )
            else:
                print(f"✅ Message envoyé avec succès à {recipient_phone}")
            return response.status_code == 200
        except Exception as e:
            print(f"⚠️ Exception lors de l'envoi du message texte : {e}")
            return False

    @staticmethod
    def send_image(
        phone_number_id, recipient_phone, image_url, caption_text="", access_token=None
    ):
        """Envoie une photo/image avec une légende facultative à partir d'un lien HTTPS public."""
        token = WhatsAppService._resolve_token(access_token)
        
        masked_token = f"{token[:10]}...{token[-5:]}" if len(token) > 15 else "INVALIDE/VIDE"
        print(f"🔍 DEBUG ENVOI IMAGE | PhoneID: {phone_number_id} | Token: {masked_token}")

        url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "image",
            "image": {"link": image_url},
        }

        if caption_text:
            payload["image"]["caption"] = caption_text

        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            if response.status_code == 200:
                print(f"🖼️ [WhatsApp Image Sent] Photo envoyée à {recipient_phone}")
                return True
            else:
                print(
                    f"❌ Erreur envoi WhatsApp Image ({response.status_code}):"
                    f" {response.text}"
                )
                return False
        except Exception as e:
            print(f"⚠️ Exception lors de l'envoi de l'image : {e}")
            return False