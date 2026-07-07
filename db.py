import os
from supabase import create_client

# Konstanten bleiben hier


def get_db_client():
    # Diese Funktion wird durch Streamlit gecacht
    URL = "https://pyyyrbhxqpsngslazzpq.supabase.co/"
    KEY = "sb_publishable_aHdbyoX1tnJZStUvry2w5A_jrTeA1jC"
    return create_client(URL, KEY)

def get_watchlist_from_db():
    supabase = get_db_client()
    try:
        response = supabase.table("watchlist").select("*").execute()
        return response.data
    except Exception as e:
        print(f"Datenbankfehler: {e}") # <-- st.error durch print ersetzt
        return []