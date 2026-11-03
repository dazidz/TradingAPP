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

# UI rendern & Spalten aufbereiten
if not df.empty:
    # 1. Sauberen Unternehmensnamen ermitteln
    if "company_name" in df.columns:
        df["unternehmen"] = df["company_name"].fillna(df.get("name", df["ticker"]))
    elif "name" in df.columns:
        df["unternehmen"] = df["name"].fillna(df["ticker"])
    else:
        df["unternehmen"] = df["ticker"]

    # 2. Echten Sektor isolieren
    sector_col = None
    for col in ["sector_watchlist", "sector", "sektor"]:
        if col in df.columns:
            sector_col = col
            break
    
    if sector_col:
        df["branchen_sektor"] = df[sector_col].fillna("Standard")
    else:
        df["branchen_sektor"] = "Standard"

    # 3. TradingView Link generieren
    def make_tv_link(row):
        t = str(row.get("gettex_ticker") or row.get("ticker") or "").strip()
        if not t:
            return ""
        if ":" not in t:
            t_symbol = f"GETTEX:{t}"
        else:
            t_symbol = t
        return f"https://www.tradingview.com/chart/?symbol={t_symbol}"

    df["tradingview"] = df.apply(make_tv_link, axis=1)

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
        
    # 4. Alle unerwünschten, doppelten oder rohen Spalten komplett entfernen
    cols_to_drop = [
        "id",
        "id_watchlist",
        "id_cache",
        "added_at",
        "strategy",
        "strategy_type",
        "strategy_kategorie",
        "name",
        "company_name",
        "sector",
        "sektor",
        "sector_watchlist",
        "sector_cache",
        "gettex_ticker",
    ]
    df_display = df_filtered.drop(columns=[col for col in cols_to_drop if col in df_display.columns])

    # 5. Saubere Reihenfolge (distance_from_ath direkt nach status platziert)
    preferred_order = [
        "unternehmen",
        "branchen_sektor",
        "aktueller_preis",
        "fair_value",
        "potential_pct",
        "status",
        "distance_from_ath",
        "eps",
        "fcf_aktie",
        "tradingview",
    ]
    existing_cols = [col for col in preferred_order if col in df_display.columns]
    other_cols = [col for col in df_display.columns if col not in existing_cols]
    df_display = df_display[existing_cols + other_cols]

    st.markdown("### 📊 Bewertungsübersicht")
    
    # 6. Interaktive Tabelle anzeigen
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "unternehmen": st.column_config.TextColumn("Unternehmen", width="medium"),
            "branchen_sektor": st.column_config.TextColumn("Sektor"),
            "aktueller_preis": st.column_config.NumberColumn("Kurs", format="€ %.2f"),
            "fair_value": st.column_config.NumberColumn("Fair Value", format="€ %.2f"),
            "potential_pct": st.column_config.NumberColumn("Potenzial", format="%.1f %%"),
            "status": st.column_config.TextColumn("Bewertung"),
            "distance_from_ath": st.column_config.NumberColumn("Abstand ATH", format="%.1f %%"),
            "eps": st.column_config.NumberColumn("EPS", format="€ %.2f"),
            "fcf_aktie": st.column_config.NumberColumn("FCF / Aktie", format="€ %.2f"),
            "tradingview": st.column_config.LinkColumn("Chart", display_text="📈 TradingView"),
        },
    )
else:
    st.warning("No data available.")