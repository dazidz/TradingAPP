import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.express as px

# Ganz oben in der app.py (vor dem restlichen Code)
st.set_page_config(layout="wide")

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# Passwort-Schutz Funktion
def check_password():
    """Überprüft das Passwort aus den Secrets"""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
        
    if not st.session_state.password_correct:
        input_pw = st.text_input("Bitte Passwort eingeben:", type="password")
        if st.button("Anmelden"):
            if input_pw == st.secrets["APP_PASSWORD"]:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("Passwort falsch.")
        return False
    return True

if check_password():
    st.title("📊 Ticker-Screener Dashboard")

    try:
        # 1. Daten holen
        response = supabase.table("signals").select("*").execute()
        df = pd.DataFrame(response.data)

        if not df.empty:
            # Mapping
            if 'signal' in df.columns:
                df = df.rename(columns={'signal': 'signal_type'})
            
            # Fehlende Spalten auffüllen (wichtig vor der Visualisierung!)
            for col in ['company_name', 'signal_type', 'candle_time', 'ticker', 'gettex_ticker', 'sector']:
                if col not in df.columns:
                    df[col] = "N/A"

            # --- NEU: Sektor-Visualisierung ---
            st.subheader("Markt-Übersicht nach Sektoren")
            
            # Sektoren zählen
            # 'N/A' Einträge werden hier als "Unbekannt" gruppiert
            temp_df = df.copy()
            temp_df.loc[temp_df['sector'] == "N/A", 'sector'] = "Unbekannt"
            sector_counts = temp_df['sector'].value_counts()
            
            # Donut-Diagramm erstellen
            fig = px.pie(
                values=sector_counts.values, 
                names=sector_counts.index, 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
            # ----------------------------------
            
            # TV-Link Logik
            if 'gettex_ticker' in df.columns:
                df['TV_Link'] = df['gettex_ticker'].apply(
                    lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else ""
                )
            
            # Spaltenreihenfolge erzwingen
            cols_to_show = ['company_name', 'signal_type', 'candle_time', 'ticker', 'gettex_ticker', 'sector', 'TV_Link']
            df = df[[c for c in cols_to_show if c in df.columns]]

            st.dataframe(
                df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "TV_Link": st.column_config.LinkColumn("TradingView", display_text="Analyse")
                }
            )
        else:
            st.write("Tabelle 'signals' ist leer.")
            
    except Exception as e:
        st.error(f"Fehler beim Laden: {e}")