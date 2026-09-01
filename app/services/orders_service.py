import datetime
import json
import os
import re
import logging
from flask import current_app
from groq import Groq
from app.services.sheets_service import SheetsService
from app.services.whatsapp_service import WhatsAppService
from app.services.cart_service import CartService

logger = logging.getLogger(__name__)

# Modèles recommandés Groq post-dépréciation 2026
PRIMARY_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
FALLBACK_MODEL = "openai/gpt-oss-120b"


class OrdersService:
    """Service d'analyse et d'enregistrement des commandes clients via Groq."""

    @staticmethod
    def get_recent_orders(tenant, limit=20):
        """Lit les commandes les plus récentes depuis l'onglet 'Commandes' du
        Google Sheets de la boutique. Retourne une liste vide (sans planter)
        si l'onglet n'existe pas encore (aucune commande passée)."""
        sheets_id = tenant.get("sheets_id")
        try:
            client = SheetsService.get_gspread_client()
            if not client:
                return []
            spreadsheet = client.open_by_key(sheets_id)
            sheet = spreadsheet.worksheet("Commandes")
            records = sheet.get_all_records()
            return list(reversed(records))[:limit]
        except Exception as e:
            logger.warning(f"⚠️ Aucune commande disponible pour l'affichage dashboard : {e}")
            return []

    @staticmethod
    def get_today_stats(tenant):
        """Calcule le nombre de commandes et le chiffre d'affaires du jour."""
        orders = OrdersService.get_recent_orders(tenant, limit=500)
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        today_orders = [o for o in orders if str(o.get("Date", "")).startswith(today_str)]

        def parse_total(row):
            try:
                return float(re.sub(r"[^\d.]", "", str(row.get("Total (DH)", "0"))))
            except ValueError:
                return 0.0

        return {
            "count_today": len(today_orders),
            "revenue_today": sum(parse_total(o) for o in today_orders),
            "count_total": len(orders),
            "revenue_total": sum(parse_total(o) for o in orders),
        }

    @staticmethod
    def extract_order_data(history, last_user_msg, last_ai_reply):
        """Interroge Groq pour extraire les données structurées de la commande au format JSON."""
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("⚠️ Clé API GROQ_API_KEY manquante dans l'environnement.")
            return {"is_order_completed": False}

        client = Groq(api_key=api_key)

        # 1. Formatage de tout l'historique de conversation
        formatted_history = ""
        if history:
            for msg in history:
                role = "Client" if msg.get("role") == "user" else "Assistant"
                formatted_history += f"{role}: {msg.get('content', '')}\n"

        prompt_extraction = f"""
        Analyse la conversation WhatsApp suivante et extrait les informations de la commande.

        HISTORIQUE COMPLET DE LA CONVERSATION :
        {formatted_history}
        Client: "{last_user_msg}"
        Assistant: "{last_ai_reply}"

        RÈGLES D'EXTRACTION STRICTES :
        1. "client_name" : Parcours TOUT l'historique pour trouver le nom complet donné par le client (ex: "Grâce Jean Pierre", "PEMBI Jean François"). Ne mets "Inconnu" QUE si aucun nom n'apparaît dans toute la conversation.
        2. "address" : Cherche l'adresse textuelle ou la géolocalisation/GPS transmise par le client.
        3. "items" : Liste explicite des produits commandés avec leurs quantités (ex: "4x T-Shirt Coton Noir, 3x Jean Slim Bleu").
        4. "total_price" : Montant total numérique uniquement (ex: "1500").
        5. "is_order_completed" : Mets true SEULEMENT SI le nom ET l'adresse/géolocalisation sont présents dans l'échange et que la commande est explicitement validée DANS LE DERNIER ÉCHANGE COURANT. Si la commande a DEJÀ été confirmée et traitée auparavant dans l'historique, mets false.

        Tu dois répondre STRICTEMENT par un objet JSON respectant cette structure :
        {{
            "is_order_completed": true ou false,
            "client_name": "Nom complet extrait",
            "address": "Adresse ou coordonnées GPS",
            "items": "Articles et quantités",
            "total_price": "Montant total numérique uniquement"
        }}
        """

        messages = [{"role": "user", "content": prompt_extraction}]

        # Tentative avec le modèle principal, puis fallback en cas d'erreur
        for model_name in [PRIMARY_MODEL, FALLBACK_MODEL]:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
                raw_content = response.choices[0].message.content.strip()
                return json.loads(raw_content)
            except Exception as e:
                logger.warning(f"⚠️ Échec d'extraction avec le modèle {model_name} : {e}")

        logger.error("❌ Échec complet d'extraction de commande après tentatives sur tous les modèles Groq.")
        return {"is_order_completed": False}

    @staticmethod
    def record_order_if_completed(
        tenant,
        phone_number_id,
        sender_phone,
        history,
        user_text,
        ai_reply,
    ):
        """Vérifie la commande, l'enregistre dans Google Sheets et notifie le vendeur via WhatsApp."""
        # Garde-fou immédiat : Si la commande est déjà validée dans le système, on abandonne
        if CartService.is_order_completed(phone_number_id, sender_phone):
            return

        order_info = OrdersService.extract_order_data(
            history, user_text, ai_reply
        )

        if order_info.get("is_order_completed"):
            client_name = order_info.get("client_name", "Inconnu")
            address = order_info.get("address", "Non spécifiée")
            items = order_info.get("items", "Non spécifié")
            total = order_info.get("total_price", "0")
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            row_data = [
                now_str,
                sender_phone,
                client_name,
                address,
                items,
                f"{total} DH",
                "En attente",
            ]

            # 1. Écriture dans Google Sheets
            sheets_id = tenant.get("sheets_id")
            success = SheetsService.append_order(sheets_id, row_data)

            if success:
                logger.info(
                    f"📦 [COMMANDE ENREGISTRÉE] Client: {client_name} | Total: {total} DH"
                )

                # --- AJOUT CRITIQUE POUR LA RELANCE ---
                # Désactiver immédiatement la relance automatique car la commande est validée
                CartService.mark_as_completed(phone_number_id, sender_phone)
                logger.info(f"🔒 Relance désactivée pour le client +{sender_phone}.")

                # 2. Récupération explicite du token d'accès WhatsApp
                access_token = (
                    tenant.get("whatsapp_access_token")
                    or tenant.get("access_token")
                    or os.getenv("WHATSAPP_ACCESS_TOKEN")
                )

                # 3. Notification WhatsApp au Vendeur
                vendor_phone = tenant.get("vendor_phone")
                if vendor_phone and access_token:
                    vendor_message = (
                        f"🚨 *NOUVELLE COMMANDE REÇUE !*\n\n"
                        f"👤 *Client :* {client_name}\n"
                        f"📞 *Téléphone :* +{sender_phone}\n"
                        f"📍 *Adresse :* {address}\n"
                        f"🛒 *Articles :* {items}\n"
                        f"💰 *Total :* {total} DH\n\n"
                        f"🕒 *Heure :* {now_str}"
                    )

                    try:
                        WhatsAppService.send_message(
                            phone_number_id=phone_number_id,
                            recipient_phone=vendor_phone,
                            message_text=vendor_message,
                            access_token=access_token,
                        )
                        logger.info(
                            f"📲 Notification WhatsApp envoyée au vendeur ({vendor_phone})"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ Erreur lors de l'envoi de la notification au vendeur : {e}"
                        )
                else:
                    logger.error(
                        f"❌ Échec envoi vendeur : vendor_phone ({vendor_phone}) ou access_token absent dans le tenant."
                    )