import time
from datetime import datetime, timedelta
from app import create_app
from app.core.database import get_db_connection
from app.services.retargeting_service import RetargetingService

def simulate_abandoned_cart():
    print("🧪 [TEST] Début de la simulation du flux de relance...")
    
    # 1. Injection d'un faux panier abandonné datant d'il y a 3 heures (pour entrer dans la fenêtre 2h-22h)
    fake_interaction_time = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Utilisez un phone_number_id correspondant à un store présent dans votre tenants.json
    fake_phone_id = "105748935955621"  
    fake_customer_phone = "22990000000" # Remplacez par votre numéro pour un vrai test WhatsApp
    fake_product = "Montre Connectée Sport"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO cart_tracking (phone_number_id, customer_phone, last_product, last_interaction, status)
                VALUES (?, ?, ?, ?, 'pending')
                ON CONFLICT(phone_number_id, customer_phone) DO UPDATE SET
                    last_product=excluded.last_product,
                    last_interaction=excluded.last_interaction,
                    status='pending'
            """, (fake_phone_id, fake_customer_phone, fake_product, fake_interaction_time))
            conn.commit()
            print(f"📥 Panier fictif injecté avec succès (Date simulée : {fake_interaction_time})")
        except Exception as e:
            print(f"❌ Erreur lors de l'injection du panier : {e}")

if __name__ == "__main__":
    app = create_app()
    
    with app.app_context():
        # Injecte la donnée de test
        simulate_abandoned_cart()
        
        # 2. Déclenchement manuel de la méthode du scheduler pour vérifier le comportement
        print("\n⚡ [TEST] Déclenchement manuel du traitement des paniers abandonnés...")
        RetargetingService.process_abandoned_carts()