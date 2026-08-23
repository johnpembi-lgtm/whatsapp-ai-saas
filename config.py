import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration centralisée de l'application Flask."""

    SECRET_KEY = os.getenv("SECRET_KEY")

    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

    WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN")
    APP_SECRET = os.getenv("APP_SECRET") or os.getenv("META_APP_SECRET")
    META_API_VERSION = os.getenv("META_API_VERSION", "v20.0")
    META_GRAPH_URL = f"https://graph.facebook.com/{META_API_VERSION}"
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    # L'API REST de Flask-APScheduler n'est pas nécessaire au fonctionnement
    # normal et reste désactivée pour ne pas exposer les commandes du scheduler.
    SCHEDULER_API_ENABLED = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() in ("1", "true", "yes")

    @classmethod
    def validate(cls):
        """Échoue au démarrage si un secret de production indispensable manque."""
        required = {
            "SECRET_KEY": cls.SECRET_KEY,
            "ADMIN_PASSWORD": cls.ADMIN_PASSWORD,
            "WEBHOOK_VERIFY_TOKEN": cls.WEBHOOK_VERIFY_TOKEN,
            "APP_SECRET": cls.APP_SECRET,
            "SUPABASE_URL": cls.SUPABASE_URL,
            "SUPABASE_KEY": cls.SUPABASE_KEY,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Variables d'environnement obligatoires manquantes : " + ", ".join(missing)
            )
