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
            
        # Spaltennamen normalisieren
        if not df_cache.empty:
            df_cache = df_cache.rename(columns=lambda x: x.lower())
        df_watchlist = df_watchlist.rename(columns=lambda x: x.lower())
        
        # Merge über den Ticker
        if not df_cache.empty:
            df = pd.merge(df_watchlist, df_cache, on="ticker", how="left", suffixes=('_watchlist', '_cache'))
        else:
            df = df_watchlist
            st.info("ℹ️ Fritz hat noch keine Cache-Daten hinterlegt. Führe einmal `python employees_test/fritz.py` aus.")

except Exception as e:
    st.error(f"Fehler beim Laden der Daten: {e}")
    df = pd.DataFrame()

# UI rendern & Spalten filtern
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
        
    # Unerwünschte Spalten entfernen (inkl. IDs, Namen, Sektoren und Timestamps)
    cols_to_drop = [
        "id",
        "id_watchlist",
        "id_cache",
        "ticker",
        "added_at",
        "strategy",
        "strategy_type",
        "strategy_kategorie",
        "name",
        "company_name",
        "sektor",
    ]
    df_display = df_filtered.drop(columns=[col for col in cols_to_drop if col in df_filtered.columns])

    # Sinnvolle Spaltenreihenfolge für die Kennzahlen festlegen
    preferred_order = [
        "aktueller_preis",
        "fair_value",
        "potential_pct",
        "status",
        "eps",
        "fcf_aktie",
    ]
    existing_cols = [col for col in preferred_order if col in df_display.columns]
    other_cols = [col for col in df_display.columns if col not in existing_cols]
    df_display = df_display[existing_cols + other_cols]

    st.markdown("### 📊 Bewertungsübersicht")
    
    # Interaktive Streamlit-Tabelle mit Währungs- und Prozentformatierung
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "aktueller_preis": st.column_config.NumberColumn("Kurs", format="€ %.2f"),
            "fair_value": st.column_config.NumberColumn("Fair Value", format="€ %.2f"),
            "potential_pct": st.column_config.NumberColumn("Potenzial", format="%.1f %%"),
            "eps": st.column_config.NumberColumn("EPS", format="€ %.2f"),
            "fcf_aktie": st.column_config.NumberColumn("FCF / Aktie", format="€ %.2f"),
            "status": st.column_config.TextColumn("Bewertung"),
        },
    )
else:
    st.warning("Keine Daten zur Anzeige verfügbar.")