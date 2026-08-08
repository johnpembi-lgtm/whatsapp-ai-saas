import time

class MessageDeduplicator:
    def __init__(self, ttl_seconds=300): # Conserve les IDs pendant 5 minutes
        self.seen_messages = {}
        self.ttl = ttl_seconds

    def is_duplicate(self, message_id: str) -> bool:
        """Vérifie si un message_id a déjà été traité récemment."""
        now = time.time()
        
        # Nettoyage automatique des identifiants expirés
        self.seen_messages = {
            msg_id: timestamp 
            for msg_id, timestamp in self.seen_messages.items() 
            if now - timestamp < self.ttl
        }

        if message_id in self.seen_messages:
            return True
        
        self.seen_messages[message_id] = now
        return False

# Instance globale réutilisable
deduplicator = MessageDeduplicator()