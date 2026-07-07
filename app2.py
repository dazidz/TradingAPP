import streamlit as st
from supabase import create_client
import pandas as pd

# Konfiguration der Seite
st.set_page_config(page_title="Ticker-Screener Dashboard", layout="wide")

st.title("📊 Ticker-Screener Dashboard")

# 1. Verbindung zu Supabase mit Fehlerprüfung
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except KeyError as e:
        st.error(f"Fehler: Secret {e} fehlt in der Streamlit-Konfiguration!")
        st.stop()
    except Exception as e:
        st.error(f"Verbindungsfehler: {e}")
        st.stop()

supabase = init_connection()

# 2. Daten laden (ersetze 'DEINE_TABELLE' durch deinen echten Tabellennamen)
@st.cache_data(ttl=600) # Cacht die Daten für 10 Minuten
def load_data():
    try:
        response = supabase.table("signals").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")
        return pd.DataFrame()

df = load_data()

# 3. Anzeige
if not df.empty:
    st.write("### Aktuelle Signale")
    st.dataframe(df, use_container_width=True)
else:
    st.warning("Keine Daten gefunden oder Tabelle leer.")

# Debug-Bereich (Nur sichtbar, wenn es Probleme gibt)
if st.checkbox("Debug: Verbindung prüfen"):
    st.write("Verbindung zu Supabase steht.")
    st.write("Spalten in der DB:", df.columns.tolist() if not df.empty else "Keine")