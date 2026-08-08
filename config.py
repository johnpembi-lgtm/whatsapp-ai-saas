import os
from dotenv import load_dotenv

# Charge les variables d'environnement depuis le fichier .env
load_dotenv()

class Config:
    """Configuration de base de l'application Flask"""
    SECRET_KEY = os.getenv("SECRET_KEY", "cle_secrete_par_defaut_dev")
    
    # Jetons Meta WhatsApp API
    WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "mon_super_token_verification_123")
    META_API_VERSION = os.getenv("META_API_VERSION", "v19.0")
    META_GRAPH_URL = f"https://graph.facebook.com/{META_API_VERSION}"
    
    # Clé API Groq Cloud (Correction ici : on appelle le nom de la variable !)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    # Clé API Google Gemini (si conservée)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # Clé API ImgBB (présente sur votre capture d'écran)
    IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

    # Chemin du fichier de configuration Multi-Tenant
    TENANTS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "stores_config", "tenants.json")