from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()
_supabase: Client | None = None

def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_ANON_KEY")
        if not url or not key:
            raise RuntimeError("Missing SUPABASE_URL / SUPABASE_ANON_KEY")
        _supabase = create_client(url, key)
    return _supabase
