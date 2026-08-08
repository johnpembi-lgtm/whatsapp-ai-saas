import os
import sqlite3

# Chemin absolu vers la base SQLite
DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../conversations.db")
)


def get_db_connection():
    """Crée et retourne une connexion SQLite configurée pour le multi-threading."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par nom
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    """Initialise les tables de la base de données SQLite."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Table de l'historique des conversations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number_id TEXT NOT NULL,
                user_phone TEXT NOT NULL,
                role TEXT NOT NULL, -- 'user' ou 'assistant'
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tenant_user 
            ON messages (phone_number_id, user_phone);
        """)

        # Table du suivi des relances / paniers abandonnés
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cart_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number_id TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_product TEXT,
                status TEXT DEFAULT 'pending', -- 'pending', 'completed', 'reminded'
                UNIQUE(phone_number_id, customer_phone)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cart_status 
            ON cart_tracking (status, last_interaction);
        """)

        conn.commit()


def save_message(phone_number_id, user_phone, role, content):
    """Enregistre un message (du client ou de l'IA)."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO messages (phone_number_id, user_phone, role, content)
                VALUES (?, ?, ?, ?)
            """,
                (phone_number_id, user_phone, role, content),
            )
            conn.commit()
    except Exception as e:
        print(
            f"❌ Erreur lors de la sauvegarde du message [{role}] pour {user_phone} : {e}"
        )


def get_conversation_history(phone_number_id, user_phone, limit=6):
    """Récupère les N derniers messages pour ce client spécifique dans l'ordre chronologique."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, content FROM (
                    SELECT role, content, id FROM messages
                    WHERE phone_number_id = ? AND user_phone = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
            """,
                (phone_number_id, user_phone, limit),
            )

            rows = cursor.fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in rows]
    except Exception as e:
        print(f"❌ Erreur lors de la récupération de l'historique pour {user_phone} : {e}")
        return []


# Initialisation au chargement du module
init_db()