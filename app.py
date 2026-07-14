import streamlit as st
from supabase import create_client
import pandas as pd
import ast

# Seiteneinstellungen
st.set_page_config(layout="wide", page_title="Ticker-Screener Dashboard")

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# Passwort-Schutz
def check_password():
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
            # Spalten-Mapping
            if 'signal' in df.columns: df = df.rename(columns={'signal': 'signal_type'})
            
            # 2. Metadaten verarbeiten (SMI/ADX aus String-JSON)
            if 'meta_data' in df.columns:
                df['meta_data'] = df['meta_data'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else {})
                meta_df = pd.json_normalize(df['meta_data'])
                df = pd.concat([df.drop('meta_data', axis=1), meta_df], axis=1)

            # TV-Link Logik
            if 'gettex_ticker' in df.columns:
                df['TV_Link'] = df['gettex_ticker'].apply(
                    lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else ""
                )
            
            # 3. Visualisierung
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🔍 SMI vs. ADX Analyse")
                if 'smi' in df.columns and 'adx' in df.columns:
                    st.scatter_chart(df, x='smi', y='adx', color='signal_type')
                else:
                    st.info("Noch keine Metadaten vorhanden.")
            
            with col2:
                st.subheader("🏢 Signale nach Sektor")
                if 'sector' in df.columns:
                    sector_counts = df['sector'].value_counts()
                    st.bar_chart(sector_counts)
                else:
                    st.write("Keine Sektoren-Daten.")

            # 4. Tabelle anzeigen
            st.subheader("📋 Signal-Liste")
            
            # Spalten-Konfiguration
            cols_to_show = ['company_name', 'signal_type', 'smi', 'adx', 'sector', 'candle_time', 'ticker', 'TV_Link']
            existing_cols = [c for c in cols_to_show if c in df.columns]
            
            st.dataframe(
                df[existing_cols], 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "TV_Link": st.column_config.LinkColumn("TradingView", display_text="Analyse"),
                    "smi": st.column_config.NumberColumn(format="%.2f"),
                    "adx": st.column_config.NumberColumn(format="%.2f")
                }
            )
        else:
            st.write("Tabelle 'signals' ist leer.")
            
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")