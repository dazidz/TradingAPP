import streamlit as st
from supabase import create_client
import pandas as pd

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# Passwort-Schutz (aus vorherigem Schritt)
PASSWORD = st.secrets["APP_PASSWORD"]

# ... [check_password Funktion bleibt gleich] ...

if check_password():
    st.title("📊 Ticker-Screener Dashboard")

    try:
        # 1. Daten holen
        response = supabase.table("signals").select("*").execute()
        df = pd.DataFrame(response.data)

        if not df.empty:
            # DEBUG: Zeige alle Spalten, die wir aus Supabase bekommen haben
            # st.write(f"Spalten in DB: {df.columns.tolist()}") 

            # Mapping
            if 'signal' in df.columns:
                df = df.rename(columns={'signal': 'signal_type'})
            
            # TV-Link Logik
            if 'gettex_ticker' in df.columns:
                df['TV_Link'] = df['gettex_ticker'].apply(
                    lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else ""
                )
            
            # WICHTIG: Wenn Spalten fehlen, füllen wir sie mit Leerwerten, 
            # damit das Dashboard nicht abstürzt oder Spalten ausblendet
            for col in ['company_name', 'signal_type', 'candle_time', 'ticker', 'gettex_ticker', 'sector']:
                if col not in df.columns:
                    df[col] = "N/A"

            # Spaltenreihenfolge erzwingen
            cols_to_show = ['company_name', 'signal_type', 'candle_time', 'ticker', 'gettex_ticker', 'sector', 'TV_Link']
            df = df[cols_to_show]

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