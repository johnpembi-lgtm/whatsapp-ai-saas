"""
Point d'entrée unique de traitement d'un message entrant, une fois le
tenant identifié. Décide UNIQUEMENT vendeur ou client, puis délègue
entièrement — aucune logique métier ici (voir doc Phase 2, section 13).
"""
import os
from flask import current_app

from app.core import database
from app.services import handover_service
from app.services.vendor_service import handle_vendor_message
from app.services.customer_processor import handle_customer_message


def resolve_access_token(tenant):
    return (
        tenant.get("whatsapp_access_token")
        or current_app.config.get("WHATSAPP_ACCESS_TOKEN")
        or os.getenv("WHATSAPP_ACCESS_TOKEN")
    )


def process(tenant, phone_number_id, sender_phone, message_data):
    """
    MESSAGE
       │
       ├── VENDEUR → vendor_service (jamais de retour vers le client processor)
       │
       └── CLIENT  → customer_processor (respecte BOT_MODE / HUMAN_MODE)
    """
    is_vendor = str(sender_phone) == str(tenant.get("vendor_phone"))
    access_token = resolve_access_token(tenant)

    if is_vendor:
        handle_vendor_message(
            phone_number_id=phone_number_id,
            vendor_phone=sender_phone,
            msg_type=message_data.get("type"),
            message_data=message_data,
            tenant=tenant,
            access_token=access_token,
        )
        return

    handle_customer_message(
        tenant=tenant,
        phone_number_id=phone_number_id,
        sender_phone=sender_phone,
        message_data=message_data,
        access_token=access_token,
    )