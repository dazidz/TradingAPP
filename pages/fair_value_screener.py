from pathlib import Path
import sys
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

# Supabase Verbindung aufbauen
try:
    URL = st.secrets["SUPABASE_URL"]
    KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(URL, KEY)
except Exception as e:
    st.error(f"Fehler beim Verbinden mit Supabase: {e}")
    st.stop()

st.title("📐 Autonomer Fair Value Screener")
st.markdown("Tagesaktuelle Bewertung des inneren Wertes nach Benjamin Graham & Warren Buffett für alle Watchlist-Titel.")

st.divider()

# Daten direkt laden und nach Value-Modellen berechnen
try:
    with st.spinner("Lade Watchlist und berechne Fair Values..."):
        response = supabase.table("watchlist").select("*").execute()
        
        if not response.data:
            st.warning("⚠️ Die Tabelle `watchlist` in Supabase ist leer.")
            st.stop()
            
        df_raw = pd.DataFrame(response.data)
        
        results = []
        for _, row in df_raw.iterrows():
            ticker = row.get("ticker") or row.get("symbol") or "UNBEKANNT"
            name = row.get("name", ticker)
            sektor = row.get("strategy_kategorie", row.get("sektor", "Standard"))
            
            # Rohdaten sicher auslesen
            preis = float(row.get("aktueller_preis") or row.get("preis") or row.get("price") or 0.0)
            eps = float(row.get("eps") or row.get("gewinn_je_aktie") or 0.0)
            fcf = float(row.get("fcf_je_aktie") or row.get("fcf") or 0.0)
            wachstum = float(row.get("erwartetes_wachstum") or 5.0)
            
            if preis <= 0:
                continue
                
            # --- Graham-Formel & Buffett Owner Earnings ---
            graham = eps * (8.5 + (2 * max(0.0, wachstum))) if eps > 0 else preis
            buffett = (fcf / 0.10) if fcf > 0 else graham
            
            # Blended Fair Value (60% Graham, 40% Buffett)
            fair_value = (graham * 0.6) + (buffett * 0.4)
            
            # Margin of Safety / Potenzial
            potential = ((fair_value - preis) / preis) * 100 if preis > 0 else 0.0
            
            if potential >= 30:
                status = "🟢 Stark Unterbewertet"
            elif potential >= 10:
                status = "🟢 Unterbewertet"
            elif potential >= -15:
                status = "🟡 Fair Bewertet"
            else:
                status = "🔴 Überbewertet"
                
            results.append({
                "Ticker": ticker,
                "Name": name,
                "Sektor": sektor,
                "Aktueller Preis": round(preis, 2),
                "Fair Value (Est.)": round(fair_value, 2),
                "Potential (%)": round(potential, 1),
                "Status": status,
                "Graham Value": round(graham, 2),
                "Owner Earnings Val": round(buffett, 2)
            })
            
        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values(by="Potential (%)", ascending=False)
            
except Exception as e:
    st.error(f"Kritischer Fehler bei der Datenverarbeitung: {e}")
    df = pd.DataFrame()

# UI-Oberfläche rendern
if not df.empty:
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filter = st.multiselect(
            "Nach Status filtern:",
            options=df["Status"].unique().tolist(),
            default=df["Status"].unique().tolist(),
        )
    
    filtered_df = df[df["Status"].isin(status_filter)]
    
    st.markdown("### 📊 Bewertungsübersicht")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

    st.markdown("### 🚀 Top Unterbewertete Chancen (Margin of Safety)")
    undervalued = filtered_df[filtered_df["Status"].str.contains("Stark Unterbewertet", na=False)]
    if not undervalued.empty:
        for _, row in undervalued.iterrows():
            st.success(
                f"**{row['Ticker']} ({row['Name']})** | Sektor: {row['Sektor']} | "
                f"Aktuell: **${row['Aktueller Preis']}** | Fair Value: **${row['Fair Value (Est.)']}** | "
                f"Potential: **{row['Potential (%)']}%**"
            )
    else:
        st.info("Aktuell befinden sich keine Titel mit 'Stark Unterbewertet' im Filterbereich.")
else:
    st.warning("Keine bewertbaren Titel in der Watchlist gefunden.")