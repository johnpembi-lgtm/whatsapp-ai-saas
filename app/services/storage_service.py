import os
import requests


class StorageService:
    """Service multi-tenant pour l'hébergement d'images via ImgBB."""

    @staticmethod
    def upload_whatsapp_media(media_id, access_token, store_id, product_name):
        """
        1. Télécharge le média depuis l'API WhatsApp Meta.
        2. L'envoie sur ImgBB avec un nom identifiant le tenant et le produit.
        3. Retourne l'URL publique HTTPS.
        """
        api_key = os.getenv("IMGBB_API_KEY")
        if not api_key:
            print("❌ IMGBB_API_KEY non configurée dans le fichier .env")
            return None

        if not access_token:
            print("❌ Access token WhatsApp manquant.")
            return None

        try:
            # 1. Récupération de l'URL temporaire de l'image auprès de Meta
            meta_url = f"https://graph.facebook.com/v20.0/{media_id}"
            headers = {"Authorization": f"Bearer {access_token}"}
            res = requests.get(meta_url, headers=headers, timeout=10)

            if res.status_code != 200:
                print(f"❌ Erreur récupération média Meta : {res.text}")
                return None

            download_url = res.json().get("url")

            # 2. Téléchargement du contenu binaire de l'image depuis Meta
            image_res = requests.get(download_url, headers=headers, timeout=15)
            if image_res.status_code != 200:
                print("❌ Échec du téléchargement de l'image Meta.")
                return None

            # 3. Nommage du fichier pour garantir l'identification du tenant
            safe_product_name = "".join(
                c if c.isalnum() else "_" for c in product_name.lower()
            ).strip("_")
            custom_filename = f"{store_id}_{safe_product_name}"

            # 4. Envoi de l'image vers ImgBB
            imgbb_url = "https://api.imgbb.com/1/upload"
            payload = {
                "key": api_key,
                "name": custom_filename,
            }
            files = {"image": image_res.content}

            response = requests.post(
                imgbb_url, data=payload, files=files, timeout=20
            )
            data = response.json()

            if response.status_code == 200 and data.get("success"):
                public_url = data["data"]["url"]
                print(f"🖼️ Image hébergée sur ImgBB pour [{store_id}] : {public_url}")
                return public_url
            else:
                print(f"❌ Erreur lors de l'upload ImgBB : {data}")
                return None

        except Exception as e:
            print(f"❌ Erreur dans StorageService (ImgBB) : {e}")
            return None