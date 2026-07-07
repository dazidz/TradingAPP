import streamlit as st
from supabase import create_client
import os

# Verbindung zu Supabase
URL = "https://pyyyrbhxqpsngslazzpq.supabase.co/"
KEY = "sb_publishable_aHdbyoX1tnJZStUvry2w5A_jrTeA1jC"
supabase = create_client(url, key)

# Passwort-Konfiguration (Setze hier dein Wunsch-Passwort)
PASSWORD = st.secrets["APP_PASSWORD"]

def check_password():
    """Gibt True zurück, wenn das Passwort korrekt ist."""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    # Login-Formular
    st.title("🔐 Ticker-Screener Login")
    input_pwd = st.text_input("Passwort eingeben", type="password")
    if st.button("Anmelden"):
        if input_pwd == PASSWORD:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Falsches Passwort!")
    return False

# Hauptprogramm starten
if check_password():

st.title("Ticker-Screener Dashboard")

# Daten laden
response = supabase.table("signals").select("*").execute()
st.dataframe(response.data)