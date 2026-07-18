import streamlit as st
from supabase import create_client
import pandas as pd
import ast
import yfinance as yf

# Seiteneinstellungen
st.set_page_config(layout="wide", page_title="Ticker-Screener Dashboard")

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# Caching für Live-Kurse (30 Minuten)
@st.cache_data(ttl=1800)
def get_all_prices(tickers):
    if not tickers: return {}
    try:
        # Bulk-Download ist massiv schneller als Einzeldownload
        data = yf.download(tickers, period="1d", interval="1h", progress=False)['Close']
        if isinstance(data, pd.Series):
            return {tickers[0]: float(data.iloc[-1])}
        return {t: float(data[t].iloc[-1]) for t in tickers if t in data.columns and not pd.isna(data[t].iloc[-1])}
    except Exception:
        return {}

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
        response = supabase.table("signals").select("*").execute()
        df = pd.DataFrame(response.data)

        if not df.empty:
            if 'signal' in df.columns: df = df.rename(columns={'signal': 'signal_type'})
            
            if 'meta_data' in df.columns:
                df['meta_data'] = df['meta_data'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else {})
                meta_df = pd.json_normalize(df['meta_data'])
                df = pd.concat([df.drop('meta_data', axis=1), meta_df], axis=1)

            if 'gettex_ticker' in df.columns:
                df['TV_Link'] = df['gettex_ticker'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else "")
            
            # Performance Berechnung
            df['entry_price'] = pd.to_numeric(df['entry_price'], errors='coerce')
            unique_tickers = df['ticker'].unique().tolist()
            
            with st.spinner("Lade Live-Kurse..."):
                price_map = get_all_prices(unique_tickers)
            
            df['current_price'] = df['ticker'].map(price_map)
            df['Performance (%)'] = ((df['current_price'] - df['entry_price']) / df['entry_price']) * 100
            
            # Visualisierung
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🔍 SMI vs. ADX Analyse")
                if 'smi' in df.columns and 'adx' in df.columns:
                    st.scatter_chart(df, x='smi', y='adx', color='signal_type')
            
            with col2:
                st.subheader("🏢 Signale nach Sektor")
                if 'sector' in df.columns:
                    st.bar_chart(df['sector'].value_counts())

            st.subheader("📋 Signal-Liste")
            cols_to_show = ['company_name', 'sector', 'signal_type', 'Performance (%)', 'smi', 'adx', 'entry_price', 'candle_time', 'TV_Link']
            existing_cols = [c for c in cols_to_show if c in df.columns]
            
            st.dataframe(
                df[existing_cols], 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "TV_Link": st.column_config.LinkColumn("TradingView", display_text="Analyse"),
                    "Performance (%)": st.column_config.NumberColumn("Performance (%)", format="%.2f%%"),
                    "entry_price": st.column_config.NumberColumn("Einstieg", format="%.2f €"),
                    "smi": st.column_config.NumberColumn("SMI", format="%.2f"),
                    "adx": st.column_config.NumberColumn("ADX", format="%.2f")
                }
            )
        else:
            st.write("Tabelle 'signals' ist leer.")
    except Exception as e:
        st.error(f"Fehler: {e}")