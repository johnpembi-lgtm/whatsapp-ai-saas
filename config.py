import os
from dotenv import load_dotenv

# Charge les variables d'environnement depuis le fichier .env
load_dotenv()

class Config:
    """Configuration centralisée de l'application Flask."""

    # Clé secrète Flask (Obligatoire)
    SECRET_KEY = os.getenv("SECRET_KEY")

    # Authentification Administration
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

    # Meta WhatsApp API (Uniformisé en v20.0)
    WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN")
    META_API_VERSION = os.getenv("META_API_VERSION", "v20.0")
    META_GRAPH_URL = f"https://graph.facebook.com/{META_API_VERSION}"
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")

    # Clés API Tiers
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

    # Base de données Supabase (Obligatoire)
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    # Chemin du fichier de configuration Multi-Tenant
    TENANTS_CONFIG_PATH = os.path.join(
        os.path.dirname(__file__), "stores_config", "tenants.json"
    )

    @classmethod
    def validate(cls):
        """Vérifie que les variables d'environnement indispensables sont bien présentes."""
        missing = []
        if not cls.SECRET_KEY:
            missing.append("SECRET_KEY")
        if not cls.WEBHOOK_VERIFY_TOKEN:
            missing.append("WEBHOOK_VERIFY_TOKEN")
        if not cls.SUPABASE_URL:
            missing.append("SUPABASE_URL")
        if not cls.SUPABASE_KEY:
            missing.append("SUPABASE_KEY")

        if missing:
            raise ValueError(
                f"CRITICAL: Les variables d'environnement suivantes sont manquantes : {', '.join(missing)}"
            )