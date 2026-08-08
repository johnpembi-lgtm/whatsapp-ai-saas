import json
import os
from flask import current_app

class TenantManager:
    """Gère la configuration multi-tenant des boutiques clientes"""

    @staticmethod
    def get_tenants():
        """Lit et renvoie le dict des boutiques à partir du fichier JSON configuré."""
        config_path = current_app.config.get("TENANTS_CONFIG_PATH")
        if not config_path or not os.path.exists(config_path):
            print(f"⚠️ Fichier de configuration non trouvé : {config_path}")
            return {}
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"❌ Erreur lors de la lecture de {config_path} : {e}")
            return {}

    @classmethod
    def save_tenants(cls, tenants_data):
        """Sauvegarde le dictionnaire complet dans le fichier JSON."""
        config_path = current_app.config.get("TENANTS_CONFIG_PATH")
        if not config_path:
            print("❌ TENANTS_CONFIG_PATH n'est pas défini dans la configuration.")
            return False

        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(tenants_data, f, indent=4, ensure_ascii=False)
            return True
        except OSError as e:
            print(f"❌ Erreur lors de l'écriture dans {config_path} : {e}")
            return False

    @classmethod
    def get_tenant_by_phone_id(cls, phone_number_id):
        """Récupère les informations d'une boutique grâce à son Phone Number ID Meta."""
        tenants = cls.get_tenants()
        tenant = tenants.get(str(phone_number_id))

        if not tenant:
            print(f"❌ Aucune boutique configurée pour le ID : {phone_number_id}")
            return None

        if not tenant.get("is_active", False):
            print(f"⚠️ La boutique [{tenant.get('store_name', tenant.get('store_id'))}] est désactivée.")
            return None

        return tenant

    @classmethod
    def add_or_update_tenant(cls, phone_number_id, store_id, vendor_phone, sheets_id, system_prompt="", is_active=True):
        """Ajoute ou met à jour une boutique dans la configuration JSON."""
        tenants = cls.get_tenants()
        clean_phone_id = str(phone_number_id).strip()
        clean_vendor = str(vendor_phone).strip().replace("+", "").replace(" ", "")

        tenants[clean_phone_id] = {
            "store_id": store_id.strip(),
            "store_name": store_id.strip(),
            "phone_number_id": clean_phone_id,
            "vendor_phone": clean_vendor,
            "sheets_id": sheets_id.strip(),
            "system_prompt": system_prompt.strip() or "Tu es un assistant commercial poli et efficace.",
            "is_active": is_active
        }
        return cls.save_tenants(tenants)