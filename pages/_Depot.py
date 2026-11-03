import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(
    layout="wide",
    page_title="VisionDZ - Investing Depot",
    page_icon="💼",
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

st.title("💼 Investing Depot & Fair Value Integration")
st.markdown("Dein Live-Depot kombiniert mit den tagesaktuellen Bewertungen von Fritz.")

st.divider()

# Daten laden (risk_depot und der Fair Value Cache)
try:
    with st.spinner("Lade Depot- und Bewertungsdaten..."):
        res_depot = supabase.table("risk_depot").select("*").execute()
        res_cache = supabase.table("fair_value_cache").select("*").execute()
        
        df_depot = pd.DataFrame(res_depot.data) if res_depot.data else pd.DataFrame()
        df_cache = pd.DataFrame(res_cache.data) if res_cache.data else pd.DataFrame()
        
        if df_depot.empty:
            st.warning("⚠️ Keine Depot-Einträge in 'risk_depot' gefunden.")
            st.stop()
            
        # Spaltennamen normalisieren
        df_depot = df_depot.rename(columns=lambda x: x.lower())
        if not df_cache.empty:
            df_cache = df_cache.rename(columns=lambda x: x.lower())
            
        # Cache-Spalten selektieren, um Konflikte zu vermeiden
        if not df_cache.empty:
            cache_cols_to_keep = ["ticker", "fair_value", "potential_pct", "status", "eps", "fcf_aktie"]
            df_cache_filtered = df_cache[[c for c in cache_cols_to_keep if c in df_cache.columns]]
            
            # Über den Ticker mit dem Depot mergen
            df = pd.merge(df_depot, df_cache_filtered, on="ticker", how="left")
        else:
            df = df_depot
            st.info("ℹ️ Hinweis: Kein Fair-Value-Cache gefunden. Bitte einmal `python employees_test/fritz.py` ausführen.")

except Exception as e:
    st.error(f"Fehler beim Laden der Daten: {e}")
    df = pd.DataFrame()

# UI rendern
if not df.empty:
    st.markdown("### 📊 Depot-Übersicht mit Fair-Value-Bewertung")
    
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "fair_value": st.column_config.NumberColumn("Fair Value", format="€ %.2f"),
            "potential_pct": st.column_config.NumberColumn("Potenzial", format="%.1f %%"),
            "status": st.column_config.TextColumn("Bewertung"),
            "aktueller_preis": st.column_config.NumberColumn("Kurs", format="€ %.2f"),
            "eps": st.column_config.NumberColumn("EPS", format="€ %.2f"),
            "fcf_aktie": st.column_config.NumberColumn("FCF / Aktie", format="€ %.2f"),
        },
    )
else:
    st.warning("Keine Daten im Depot verfügbar.")