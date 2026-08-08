import json
import os
from groq import Groq


class AIService:

    @staticmethod
    def generate_response(
        system_prompt, catalog, user_message, history=None
    ):
        if history is None:
            history = []

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("❌ Erreur AIService : GROQ_API_KEY manquant dans .env")
            return "Désolé, le service IA est indisponible pour le moment."

        client = Groq(api_key=api_key)

        # 1. Mise en forme propre et claire du catalogue
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

        # 2. Directives Système Optimisées pour l'Expérience Client (CX)
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
   - Fais le lien avec des synonymes (ex: "pantalon" -> "Jean Slim Bleu", "tshirt" -> "T-Shirt Coton"). Ne dis jamais qu'un article est indisponible s'il y a un équivalent évident dans le catalogue.

2. GESTION DES PHOTOS [SEND_IMAGE: <url>] :
   - Si le client demande explicitement une photo (ex: "montre-moi", "photo", "voir la chemise"), ajoute [SEND_IMAGE: <url_exacte>] dans ta réponse.
   - Si le client demande seulement le prix ou le stock, ne mets AUCUN tag d'image.
   - N'invente jamais d'URL.

3. PROCESSUS DE COMMANDE ET COLLECTE D'INFORMATIONS :
   - Dès que le client confirme vouloir commander, guide-le pas à pas sans le braquer.
   - Tu dois obtenir DEUX informations obligatoires pour valider sa commande :
     1. Son **Nom et Prénom**
     2. Son **Adresse de livraison** (ou sa position GPS WhatsApp)
   - Si le client donne son nom mais pas son adresse, remercie-le et demande-lui poliment son adresse.
   - Si le client donne son adresse mais pas son nom, demande-lui poliment son nom complet.

4. RÉCAPITULATIF ET VALIDATION :
   - Dès que tu as LE NOM ET L'ADRESSE, fais un récapitulatif clair :
     * Articles + Quantités
     * Calcul exact du total (Quantité × Prix) en DH
     * Nom du destinataire et Adresse
   - Confirme-lui que sa commande est bien enregistrée et qu'il recevra son colis sous peu (Paiement à la livraison).
"""

        messages = [{"role": "system", "content": system_instruction}]

        # 3. Injection de l'historique
        for msg in history:
            role = "assistant" if msg.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": msg.get("content", "")})

        # 4. Message courant
        messages.append({"role": "user", "content": user_message})

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.2,  # Légère flexibilité pour un ton plus humain
                max_tokens=300,
            )

            res_content = response.choices[0].message.content.strip()

            # Nettoyage des doublons de monnaie
            while "DH DH" in res_content:
                res_content = res_content.replace("DH DH", "DH")

            return res_content

        except Exception as e:
            print(f"❌ Erreur Groq AIService : {e}")
            return "Désolé, je rencontre des difficultés pour répondre."