import streamlit as st
from supabase import create_client
import pandas as pd

# 1. Konfiguration
st.set_page_config(page_title="Ticker-Screener", layout="wide")

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# Passwort-Konfiguration
PASSWORD = st.secrets["APP_PASSWORD"]

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.title("🔐 Ticker-Screener Login")
    input_pwd = st.text_input("Passwort eingeben", type="password")
    if st.button("Anmelden"):
        if input_pwd == PASSWORD:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Falsches Passwort!")
    return False

# Hauptprogramm
if check_password():
    st.title("📊 Ticker-Screener Dashboard")

    # 2. Daten laden
    try:
        response = supabase.table("signals").select("*").execute()
        df = pd.DataFrame(response.data)

        if not df.empty:
            # Spalte 'signal' zu 'signal_type' umbenennen, falls vorhanden
            if 'signal' in df.columns:
                df = df.rename(columns={'signal': 'signal_type'})
            
            # Wunsch-Reihenfolge definieren
            cols_to_show = ['signal_type', 'company_name', 'sector', 'candle_time', 'ticker']
            
            # Filtern: Nur existierende Spalten wählen, die auch in der Liste sind
            existing_cols = [c for c in cols_to_show if c in df.columns]
            df = df[existing_cols]
            
            # Leere Werte in candle_time füllen
            if 'candle_time' in df.columns:
                df['candle_time'] = df['candle_time'].fillna("Keine Zeit")
            
            # Anzeige
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.write("Keine Daten in der Tabelle 'signals' gefunden.")
            
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")