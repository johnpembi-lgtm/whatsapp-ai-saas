import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠️ Supabase non configuré. Assurez-vous d'avoir SUPABASE_URL et SUPABASE_KEY dans .env")


class SupabaseTenantManager:

    @staticmethod
    def get_tenants():
        if not supabase:
            return []
        res = supabase.table("tenants").select("*").execute()
        return res.data

    @staticmethod
    def get_tenant_by_phone_id(phone_number_id):
        if not supabase:
            return None
        res = supabase.table("tenants").select("*").eq("phone_number_id", phone_number_id).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def add_or_update_tenant(phone_number_id, store_id, vendor_phone, sheets_id, system_prompt):
        if not supabase:
            return False
        payload = {
            "phone_number_id": phone_number_id,
            "store_id": store_id,
            "vendor_phone": vendor_phone,
            "sheets_id": sheets_id,
            "system_prompt": system_prompt
        }
        # Upsert (Insère ou met à jour si la clé existe)
        res = supabase.table("tenants").upsert(payload, on_conflict="phone_number_id").execute()
        return bool(res.data)


class SupabaseChatHistory:

    @staticmethod
    def save_message(phone_number_id, user_phone, role, content):
        if not supabase:
            return
        payload = {
            "phone_number_id": phone_number_id,
            "user_phone": user_phone,
            "role": role,
            "content": content
        }
        supabase.table("messages").insert(payload).execute()

    @staticmethod
    def get_history(phone_number_id, user_phone, limit=10):
        if not supabase:
            return []
        res = supabase.table("messages") \
            .select("role, content") \
            .eq("phone_number_id", phone_number_id) \
            .eq("user_phone", user_phone) \
            .order("created_at", desc=False) \
            .limit(limit) \
            .execute()
        return res.data