import streamlit as st
from supabase import create_client
import pandas as pd
import ast
import yfinance as yf
import altair as alt

# Seiteneinstellungen
st.set_page_config(layout="wide", page_title="Ticker-Screener Dashboard")

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# Caching für Live-Kurse (30 Minuten)
@st.cache_data(ttl=1800)
def get_all_prices(tickers):
    prices = {}
    for ticker in tickers:
        try:
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(period="1d")
            if not hist.empty:
                prices[ticker] = float(hist['Close'].iloc[-1])
        except Exception:
            continue
    return prices

# Caching für EMA-Abstand (30 Minuten)
@st.cache_data(ttl=1800)
def get_ema_stats_bulk(tickers):
    stats = {}
    if not tickers: return stats
    data = yf.download(tickers, period="1mo", interval="1d", progress=False)['Close']
    for ticker in tickers:
        try:
            series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
            if len(series) >= 20:
                ema20 = series.ewm(span=20, adjust=False).mean().iloc[-1]
                stats[ticker] = float(((series.iloc[-1] - ema20) / ema20) * 100)
        except Exception: stats[ticker] = None
    return stats

# Passwort-Schutz
def check_password():
    if "password_correct" not in st.session_state: st.session_state.password_correct = False
    if not st.session_state.password_correct:
        input_pw = st.text_input("Bitte Passwort eingeben:", type="password")
        if st.button("Anmelden"):
            if input_pw == st.secrets["APP_PASSWORD"]:
                st.session_state.password_correct = True
                st.rerun()
            else: st.error("Passwort falsch.")
        return False
    return True

# --- HAUPTPROGRAMM ---
if check_password():
    st.title("📊 Ticker-Screener Dashboard")

    try:
        response = supabase.table("signals").select("*").execute()
        df = pd.DataFrame(response.data)

        if not df.empty:
            # Daten aufbereiten
            if 'signal' in df.columns: df = df.rename(columns={'signal': 'signal_type'})
            if 'status' not in df.columns: df['status'] = 'signal'
            
            # Kurse & EMA laden
            unique_tickers = df['ticker'].unique().tolist()
            price_map = get_all_prices(unique_tickers)
            ema_map = get_ema_stats_bulk(unique_tickers)
            df['current_price'] = df['ticker'].map(price_map)
            df['entry_price'] = pd.to_numeric(df['entry_price'], errors='coerce')
            df['Performance (%)'] = ((df['current_price'] - df['entry_price']) / df['entry_price']) * 100
            df['EMA20_Dist_%'] = df['ticker'].map(ema_map)

            # Tabs
            tab1, tab2, tab3 = st.tabs(["⭐ Favoriten", "🚀 Über EMA20", "⚠️ Unter EMA20"])

            # Spaltenkonfiguration für das DataFrame (ermöglicht Sortierung)
            col_config = {
                "Performance (%)": st.column_config.NumberColumn(format="%.2f%%"),
                "EMA20_Dist_%": st.column_config.NumberColumn(format="%.2f%%"),
                "entry_price": st.column_config.NumberColumn(format="%.2f €"),
                "TV_Link": st.column_config.LinkColumn("Chart", display_text="Link")
            }

            def show_table(df_subset):
                edited_df = st.data_editor(
                    df_subset[['ticker', 'company_name', 'Performance (%)', 'EMA20_Dist_%', 'entry_price', 'status']],
                    column_config=col_config,
                    hide_index=True,
                    use_container_width=True
                )
                # Hier könntest du bei Bedarf Aktionen für Favoriten einbauen

            with tab1:
                show_table(df[df['status'] == 'favorite'])
            with tab2:
                show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] >= 0)])
            with tab3:
                show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] < 0)])

        else:
            st.info("Datenbank ist leer.")
    except Exception as e:
        st.error(f"Fehler: {e}")