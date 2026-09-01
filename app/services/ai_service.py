import json
import os
import logging
from groq import Groq
import httpx

logger = logging.getLogger(__name__)

# Modèles actifs 2026 post-dépréciation Groq
PRIMARY_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
FALLBACK_MODEL = "openai/gpt-oss-120b"


class AIService:

    @staticmethod
    def _get_client():
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.error("❌ Erreur AIService : GROQ_API_KEY manquant dans .env")
            return None
        try:
            http_client = httpx.Client(timeout=15.0)
            return Groq(api_key=api_key, http_client=http_client)
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'initialisation du client Groq : {e}")
            return None

    @classmethod
    def generate_response(
        cls, system_prompt, catalog, user_message, history=None
    ):
        if history is None:
            history = []

        client = cls._get_client()
        if not client:
            return "Désolé, le service IA est indisponible pour le moment."

        # 1. Mise en forme du catalogue
        catalog_text = ""
        if isinstance(catalog, list):
            for item in catalog:
                name = (
                    item.get("nom")
                    or item.get("product_name")
                    or item.get("article")
                    or "Article"
                )
                price = (
                    item.get("prix")
                    if item.get("prix") is not None
                    else item.get("price", "")
                )
                stock = item.get("stock") or "Disponible"
                image_url = item.get("image_url") or item.get("image") or ""

                price_str = str(price).strip()
                if price_str and not price_str.upper().endswith("DH"):
                    price_str = f"{price_str} DH"

                line = f"- {name} : {price_str} | Stock: {stock}"
                if image_url:
                    line += f" | Image: {image_url}"
                catalog_text += line + "\n"

        elif isinstance(catalog, dict):
            catalog_text = json.dumps(catalog, ensure_ascii=False, indent=2)
        else:
            catalog_text = str(catalog)

        # 2. Directives Système
        system_instruction = f"""{system_prompt}

CATALOGUE DISPONIBLE EN BOUTIQUE :
{catalog_text}

TON RÔLE ET TON STYLE DE COMMUNICATION :
- Tu es un conseiller de vente chaleureux, efficace et très poli sur WhatsApp.
- Fais des réponses COURTES, CLAIRES et adaptées au format mobile (WhatsApp).
- Utilise des emojis de manière naturelle et professionnelle.

RÈGLES DU PARCOURS CLIENT :

1. ACCUEIL ET CONSEIL :
   - Réponds directement aux questions du client sur les produits, prix ou stocks.
   - Fais le lien avec des synonymes (ex: "pantalon" -> "Jean Slim Bleu", "tshirt" -> "T-Shirt Coton"). Ne dis jamais qu'un article est indisponible s'il y a un équivalent officiel ou un équivalent évident dans le catalogue.

2. GESTION DES PHOTOS [SEND_IMAGE: <url>] :
   - Si le client demande explicitement une photo (ex: "montre-moi", "photo", "voir la chemise"), ajoute [SEND_IMAGE: <url_exacte>] dans ta réponse.
   - Si le client demande seulement le prix ou le stock, ne mets AUCUN tag d'image.
   - N'invente jamais d'URL.

3. PROCESSUS DE COMMANDE ET COLLECTE D'INFORMATIONS :
   - Dès que le client confirme vouloir commander, guide-le pas à pas sans le braquer.
   - Tu dois obtenir DEUX informations obligatoires pour formaliser sa demande :
     1. Son **Nom et Prénom**
     2. Son **Adresse** (ou ville / position GPS)
   - Si le client donne son nom mais pas son adresse, remercie-le et demande-lui poliment son adresse.
   - Si le client donne son adresse mais pas son nom, demande-lui poliment son nom complet.

4. RÉCAPITULATIF ET CHOIX DU MODE DE LIVRAISON :
   - Dès que tu as LE NOM ET L'ADRESSE (ou la ville), fais un récapitulatif clair :
     * Articles + Quantités
     * Calcul exact du total (Quantité × Prix) en DH
     * Nom du destinataire et Adresse
   - Propose EXPLICITEMENT les deux options au client s'il ne l'a pas précisé :
     * Option 1 : **Livraison à domicile** (Paiement cash à la livraison)
     * Option 2 : **Retrait directement en boutique**
   - Demande-lui poliment quelle option il préfère pour valider définitivement la commande.

5. APRES LA VALIDATION DE LA COMMANDE :
   - Si la commande a déjà été confirmée dans l'historique, NE RELANCE PAS l'accueil, NE PROPOSE PLUS le catalogue.
   - Si le client réécrit juste après, réponds-lui poliment en lui précisant que sa commande est bien prise en compte et en cours de préparation.
"""

        messages = [{"role": "system", "content": system_instruction}]

        for msg in history:
            role = "assistant" if msg.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": msg.get("content", "")})

        messages.append({"role": "user", "content": user_message})

        try:
            return cls._call_groq_api(client, PRIMARY_MODEL, messages, max_tokens=300, temperature=0.2)
        except Exception as e:
            logger.warning(f"⚠️ Échec du modèle principal ({PRIMARY_MODEL}): {e}. Tentative avec {FALLBACK_MODEL}...")
            try:
                return cls._call_groq_api(client, FALLBACK_MODEL, messages, max_tokens=300, temperature=0.2)
            except Exception as err:
                logger.error(f"❌ Erreur critique Groq AIService : {err}")
                return "Désolé, je rencontre des difficultés pour répondre."

    @classmethod
    def extract_order(cls, history_text: str):
        client = cls._get_client()
        if not client:
            return None

        prompt = (
            "Analyse cette conversation WhatsApp et extrait la commande au format JSON strict avec les clés : "
            "'client_name', 'client_address', 'items' (liste d'objets avec 'name', 'quantity', 'price'), "
            "'total_amount', 'delivery_type'. Si aucune commande complète n'est trouvée, retourne un objet vide {}.\n\n"
            f"CONVERSATION :\n{history_text}"
        )

        messages = [
            {"role": "system", "content": "Tu es un extracteur de données JSON strict."},
            {"role": "user", "content": prompt}
        ]

        try:
            raw_res = cls._call_groq_api(client, PRIMARY_MODEL, messages, max_tokens=500, temperature=0.0)
            return json.loads(raw_res)
        except Exception as e:
            logger.warning(f"⚠️ Échec extraction avec {PRIMARY_MODEL}, tentative fallback...")
            try:
                raw_res = cls._call_groq_api(client, FALLBACK_MODEL, messages, max_tokens=500, temperature=0.0)
                return json.loads(raw_res)
            except Exception as err:
                logger.error(f"❌ Erreur lors de l'extraction de la commande via Groq : {err}")
                return None

    @staticmethod
    def _call_groq_api(client, model, messages, max_tokens=300, temperature=0.2):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        res_content = response.choices[0].message.content.strip()
        while "DH DH" in res_content:
            res_content = res_content.replace("DH DH", "DH")
        return res_content