import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(
    layout="wide",
    page_title="VisionDZ - Fair Value Screener",
    page_icon="📐",
)

if not st.session_state.get("password_correct", False):
    st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
    st.stop()

# Supabase Verbindung
try:
    URL = st.secrets["SUPABASE_URL"]
    KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(URL, KEY)
except Exception as e:
    st.error(f"Fehler beim Verbinden mit Supabase: {e}")
    st.stop()

st.title("📐 Autonomer Fair Value Screener")
st.markdown("Tagesaktuelle Bewertung des inneren Wertes (Graham & Buffett) – von Fritz im Hintergrund aufbereitet.")

st.divider()

# Daten laden und via Pandas-Merge zusammenführen
try:
    with st.spinner("Lade aufbereitete Daten..."):
        res_watchlist = supabase.table("watchlist").select("*").execute()
        res_cache = supabase.table("fair_value_cache").select("*").execute()
        
        df_watchlist = pd.DataFrame(res_watchlist.data) if res_watchlist.data else pd.DataFrame()
        df_cache = pd.DataFrame(res_cache.data) if res_cache.data else pd.DataFrame()
        
        if df_watchlist.empty:
            st.warning("⚠️ Die Watchlist ist leer.")
            st.stop()
            
        # Merge über den Ticker
        if not df_cache.empty:
            df_cache = df_cache.rename(columns=lambda x: x.lower())
            df_watchlist = df_watchlist.rename(columns=lambda x: x.lower())
            df = pd.merge(df_watchlist, df_cache, on="ticker", how="left", suffixes=('', '_cache'))
        else:
            df = df_watchlist
            st.info("ℹ️ Fritz hat noch keine Cache-Daten hinterlegt. Führe einmal `python employees_test/fritz.py` aus.")

except Exception as e:
    st.error(f"Fehler beim Laden der Daten: {e}")
    df = pd.DataFrame()

# UI rendern
if not df.empty:
    status_col = "status" if "status" in df.columns else None
    
    if status_col:
        statuses = df[status_col].dropna().unique().tolist()
        if statuses:
            selected_status = st.multiselect(
                "Nach Status filtern:",
                options=statuses,
                default=statuses,
            )
            df_filtered = df[df[status_col].isin(selected_status)]
        else:
            df_filtered = df
    else:
        df_filtered = df
        
    st.markdown("### 📊 Bewertungsübersicht")
    st.dataframe(df_filtered, use_container_width=True, hide_index=True)
else:
    st.warning("Keine Daten zur Anzeige verfügbar.")