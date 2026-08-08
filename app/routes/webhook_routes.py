import os
import re
import threading
from collections import deque
from flask import Blueprint, request, jsonify, current_app

from app.core.tenant_manager import TenantManager
from app.services.ai_service import AIService
from app.services.whatsapp_service import WhatsAppService
from app.services.sheets_service import SheetsService
from app.services.orders_service import OrdersService
from app.services.storage_service import StorageService
from app.services.cart_service import CartService  # <-- AJOUT : Import du service de panier
from app.core.database import save_message, get_conversation_history

webhook_bp = Blueprint("webhook", __name__)

# Anti-doublon FIFO thread-safe à l'échelle du module
MAX_PROCESSED_MESSAGES = 2000
PROCESSED_MESSAGE_IDS = set()
PROCESSED_QUEUE = deque()
PROCESSED_LOCK = threading.Lock()


def parse_vendor_caption(caption):
    """
    Extrait dynamiquement les champs depuis le texte envoyé par le vendeur.
    Exemple : "Nom: T-Shirt Noir | Description: Col V en coton | Prix: 150 | Stock: 20"
    """
    data = {"nom": "", "description": "", "prix": 0, "stock": 0}
    if not caption:
        return data

    parts = caption.split("|")
    for part in parts:
        if ":" in part:
            key, val = part.split(":", 1)
            key = key.strip().lower()
            val = val.strip()

            if key in ["nom", "article", "produit"]:
                data["nom"] = val
            elif key in ["description", "desc"]:
                data["description"] = val
            elif key in ["prix", "price"]:
                try:
                    data["prix"] = float(re.sub(r"[^\d.]", "", val))
                except ValueError:
                    data["prix"] = 0
            elif key in ["stock", "quantite", "quantité"]:
                try:
                    data["stock"] = int(re.sub(r"\D", "", val))
                except ValueError:
                    data["stock"] = 0
    return data


def process_message_async(app, tenant, phone_number_id, sender_phone, message_data):
    """Traitement en arrière-plan avec contexte d'application Flask."""
    with app.app_context():
        try:
            msg_type = message_data.get("type")
            is_vendor = str(sender_phone) == str(tenant.get("vendor_phone"))
            store_id = tenant.get("store_id", "default_store")
            sheets_id = tenant.get("sheets_id")

            # Récupération prioritaire du token d'accès
            access_token = (
                tenant.get("whatsapp_access_token")
                or current_app.config.get("WHATSAPP_ACCESS_TOKEN")
                or os.getenv("WHATSAPP_ACCESS_TOKEN")
            )

            # --- CAS 1 : C'EST LE VENDEUR QUI MET À JOUR UN PRODUIT ---
            if is_vendor:
                # Sous-cas A : Vendeur envoie une IMAGE avec légende
                if msg_type == "image":
                    media_id = message_data.get("image", {}).get("id")
                    caption = message_data.get("image", {}).get("caption", "")
                    parsed = parse_vendor_caption(caption)
                    product_name = parsed.get("nom")

                    if not product_name:
                        WhatsAppService.send_message(
                            phone_number_id=phone_number_id,
                            recipient_phone=sender_phone,
                            message_text=(
                                "⚠️ *Format d'image incorrect pour le catalogue.*\n\n"
                                "Veuillez ajouter une légende sous la photo au format :\n"
                                "`Nom: [Nom] | Description: [Texte] | Prix: [150] | Stock: [10]`"
                            ),
                            access_token=access_token,
                        )
                        return

                    image_url = StorageService.upload_whatsapp_media(
                        media_id=media_id,
                        access_token=access_token,
                        store_id=store_id,
                        product_name=product_name,
                    )

                    if image_url:
                        success = SheetsService.add_or_update_product(
                            sheets_id=sheets_id,
                            product_name=product_name,
                            description=parsed.get("description", ""),
                            price=parsed.get("prix", 0),
                            stock=parsed.get("stock", 0),
                            image_url=image_url,
                        )
                        if success:
                            WhatsAppService.send_message(
                                phone_number_id=phone_number_id,
                                recipient_phone=sender_phone,
                                message_text=f"✅ *Produit avec photo '{product_name}' enregistré dans Google Sheets !*",
                                access_token=access_token,
                            )
                        else:
                            WhatsAppService.send_message(
                                phone_number_id=phone_number_id,
                                recipient_phone=sender_phone,
                                message_text="❌ Erreur d'enregistrement Google Sheets.",
                                access_token=access_token,
                            )
                    return

                # Sous-cas B : Vendeur envoie un TEXTE (doit contenir Nom, Description, Prix, Stock)
                elif msg_type == "text":
                    text_body = message_data.get("text", {}).get("body", "")
                    if "nom:" in text_body.lower() or "article:" in text_body.lower():
                        parsed = parse_vendor_caption(text_body)
                        product_name = parsed.get("nom")
                        description = parsed.get("description")

                        # Vérification des champs obligatoires
                        if product_name and description:
                            success = SheetsService.add_or_update_product(
                                sheets_id=sheets_id,
                                product_name=product_name,
                                description=description,
                                price=parsed.get("prix", 0),
                                stock=parsed.get("stock", 0),
                                image_url="",  # Pas d'image fournie via texte simple
                            )
                            if success:
                                WhatsAppService.send_message(
                                    phone_number_id=phone_number_id,
                                    recipient_phone=sender_phone,
                                    message_text=f"✅ *Produit '{product_name}' enregistré avec succès !*",
                                    access_token=access_token,
                                )
                                return
                        else:
                            # Message d'aide si la description ou le nom manque
                            WhatsAppService.send_message(
                                phone_number_id=phone_number_id,
                                recipient_phone=sender_phone,
                                message_text=(
                                    "⚠️ *Format texte incomplet.*\n\n"
                                    "L'ajout par texte nécessite obligatoirement les 4 champs suivants :\n"
                                    "`Nom: [Nom] | Description: [Texte] | Prix: [150] | Stock: [20]`"
                                ),
                                access_token=access_token,
                            )
                            return

            # --- CAS 2 : TRAITEMENT CLASSIQUE CLIENT (TEXTE / LOCALISATION) ---
            user_text = ""
            if msg_type == "text":
                user_text = message_data.get("text", {}).get("body", "")
            elif msg_type == "location":
                loc = message_data.get("location", {})
                lat = loc.get("latitude")
                lng = loc.get("longitude")
                name = loc.get("name", "")
                address = loc.get("address", "")
                
                if lat and lng:
                    details = f" ({name} - {address})".strip(" ()")
                    user_text = f"[LOCALISATION PARTAGÉE : Lat {lat}, Long {lng}{f' - {details}' if details else ''} | Google Maps: https://maps.google.com/?q={lat},{lng}]"
                else:
                    print("⚠️ Payload de localisation reçu mais coordonnées manquantes.")
                    return
            else:
                return

            # --- AJOUT CRITIQUE POUR LA RELANCE ---
            # Initialise ou réactive le statut du panier du client à chaque nouveau message reçu
            CartService.update_interaction(phone_number_id, sender_phone)

            # 1. Historique récent
            history = get_conversation_history(phone_number_id, sender_phone, limit=6)

            # 2. Récupérer le catalogue produit
            catalog = SheetsService.fetch_catalog(sheets_id)

            # 3. Générer la réponse IA
            ai_reply = AIService.generate_response(
                tenant.get("system_prompt"),
                catalog,
                user_text,
                history=history,
            )

            print(f"🤖 Réponse IA générée pour [{sender_phone}] : {ai_reply}")

            # 4. Sauvegarder dans la base SQLite
            save_message(phone_number_id, sender_phone, "user", user_text)
            save_message(phone_number_id, sender_phone, "assistant", ai_reply)

            # 5. Détecter si l'IA demande l'envoi d'une image au client
            image_match = re.search(r"\[SEND_IMAGE:\s*(https?://[^\s\]]+)\]", ai_reply)

            if image_match:
                image_url = image_match.group(1)
                clean_reply = re.sub(r"\[SEND_IMAGE:\s*https?://[^\s\]]+\]", "", ai_reply).strip()

                WhatsAppService.send_image(
                    phone_number_id=phone_number_id,
                    recipient_phone=sender_phone,
                    image_url=image_url,
                    caption_text=clean_reply,
                    access_token=access_token,
                )
            else:
                WhatsAppService.send_message(
                    phone_number_id=phone_number_id,
                    recipient_phone=sender_phone,
                    message_text=ai_reply,
                    access_token=access_token,
                )

            # 6. Détecter et enregistrer la commande si complète
            OrdersService.record_order_if_completed(
                tenant=tenant,
                phone_number_id=phone_number_id,
                sender_phone=sender_phone,
                history=history,
                user_text=user_text,
                ai_reply=ai_reply,
            )

        except Exception as e:
            print(f"❌ Erreur lors du traitement asynchrone du message : {e}")


@webhook_bp.route("/webhook", methods=["GET"])
def verify_webhook():
    """Validation initiale du Webhook Meta."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == current_app.config.get("WEBHOOK_VERIFY_TOKEN"):
            print("✅ Webhook Meta vérifié avec succès !")
            return challenge, 200
        else:
            print("❌ Token Webhook invalide.")
            return jsonify({"error": "Token de vérification invalide"}), 403

    return jsonify({"error": "Requête invalide"}), 400


@webhook_bp.route("/webhook", methods=["POST"])
def handle_webhook():
    """Réception des webhooks WhatsApp en temps réel."""
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "Aucune donnée reçue"}), 400

    if data.get("object") == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")
                messages = value.get("messages", [])

                if messages:
                    for message in messages:
                        msg_id = message.get("id")

                        # Anti-doublon FIFO thread-safe
                        with PROCESSED_LOCK:
                            if msg_id in PROCESSED_MESSAGE_IDS:
                                print(f"⚠️ Message doublon ignoré : {msg_id}")
                                continue

                            PROCESSED_MESSAGE_IDS.add(msg_id)
                            PROCESSED_QUEUE.append(msg_id)

                            if len(PROCESSED_QUEUE) > MAX_PROCESSED_MESSAGES:
                                oldest_id = PROCESSED_QUEUE.popleft()
                                PROCESSED_MESSAGE_IDS.remove(oldest_id)

                        sender_phone = message.get("from")

                        tenant = TenantManager.get_tenant_by_phone_id(phone_number_id)
                        if tenant:
                            app = current_app._get_current_object()
                            threading.Thread(
                                target=process_message_async,
                                args=(app, tenant, phone_number_id, sender_phone, message),
                            ).start()

        return jsonify({"status": "success"}), 200

    return jsonify({"status": "not_a_whatsapp_event"}), 404