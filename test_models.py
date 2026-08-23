"""Petit diagnostic manuel Gemini. Non utilisé par l'application Pemby."""
import os
from dotenv import load_dotenv


def main():
    from google import genai

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY manquante.")

    client = genai.Client(api_key=api_key)
    print("--- Modèles Gemini disponibles ---")
    try:
        for model in client.models.list():
            print(model.name)
    except Exception as exc:
        print(f"Erreur : {exc}")


if __name__ == "__main__":
    main()
