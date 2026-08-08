from datetime import datetime
from app.core.database import get_db_connection

class CartService:
    @staticmethod
    def update_interaction(phone_number_id, customer_phone, last_product=None):
        """Met à jour l'horodatage de la dernière interaction pour le suivi de relance."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                
                query = """
                    INSERT INTO cart_tracking (phone_number_id, customer_phone, last_interaction, last_product, status)
                    VALUES (?, ?, ?, ?, 'pending')
                    ON CONFLICT(phone_number_id, customer_phone) DO UPDATE SET
                        last_interaction = ?,
                        last_product = COALESCE(?, last_product),
                        status = CASE WHEN status = 'reminded' THEN 'pending' ELSE status END
                """
                cursor.execute(query, (phone_number_id, customer_phone, now, last_product, now, last_product))
                conn.commit()
        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour de l'interaction panier : {e}")

    @staticmethod
    def mark_as_completed(phone_number_id, customer_phone):
        """Marque une commande comme finalisée pour annuler la relance."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE cart_tracking 
                    SET status = 'completed' 
                    WHERE phone_number_id = ? AND customer_phone = ?
                """, (phone_number_id, customer_phone))
                conn.commit()
        except Exception as e:
            print(f"❌ Erreur lors de la validation du panier : {e}")