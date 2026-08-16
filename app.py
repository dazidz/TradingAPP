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

# Caching für Kurse & EMA
@st.cache_data(ttl=1800)
def get_all_prices(tickers):
    prices = {}
    for ticker in tickers:
        try:
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(period="1d")
            if not hist.empty:
                prices[ticker] = float(hist['Close'].iloc[-1])
        except Exception: continue
    return prices

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
            if 'signal' in df.columns: df = df.rename(columns={'signal': 'signal_type'})
            if 'status' not in df.columns: df['status'] = 'signal'
            
            # TradingView Link erstellen
            if 'gettex_ticker' in df.columns:
                df['TV_Link'] = df['gettex_ticker'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else "")
            
            unique_tickers = df['ticker'].unique().tolist()
            price_map = get_all_prices(unique_tickers)
            ema_map = get_ema_stats_bulk(unique_tickers)
            df['current_price'] = df['ticker'].map(price_map)
            df['entry_price'] = pd.to_numeric(df['entry_price'], errors='coerce')
            df['Performance (%)'] = ((df['current_price'] - df['entry_price']) / df['entry_price']) * 100
            df['EMA20_Dist_%'] = df['ticker'].map(ema_map)

            def show_table(df_subset, is_fav_view=False):
                df_editor = df_subset.copy()
                df_editor['Action'] = False 
                
                # Wir zeigen Action, Ticker, Name, Performance, Preis, EMA-Dist und den Link
                edited_df = st.data_editor(
                    df_editor[['Action', 'ticker', 'company_name', 'Performance (%)', 'entry_price', 'EMA20_Dist_%', 'TV_Link']],
                    column_config={
                        "Action": st.column_config.CheckboxColumn(
                            "Löschen" if is_fav_view else "Zu Favoriten",
                            default=False
                        ),
                        "Performance (%)": st.column_config.NumberColumn(format="%.2f%%"),
                        "EMA20_Dist_%": st.column_config.NumberColumn(format="%.2f%%"),
                        "entry_price": st.column_config.NumberColumn(format="%.2f €"),
                        "TV_Link": st.column_config.LinkColumn("Chart", display_text="Analyse")
                    },
                    hide_index=True,
                    use_container_width=True
                )

                changed = edited_df[edited_df['Action'] == True]
                if not changed.empty:
                    for _, row in changed.iterrows():
                        target_id = df_subset[df_subset['ticker'] == row['ticker']]['id'].iloc[0]
                        if is_fav_view:
                            supabase.table("signals").delete().eq("id", target_id).execute()
                        else:
                            supabase.table("signals").update({"status": "favorite"}).eq("id", target_id).execute()
                        st.rerun()

            tab1, tab2, tab3 = st.tabs(["⭐ Favoriten", "🚀 Über EMA20", "⚠️ Unter EMA20"])

            with tab1:
                show_table(df[df['status'] == 'favorite'], is_fav_view=True)
            with tab2:
                show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] >= 0)], is_fav_view=False)
            with tab3:
                show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] < 0)], is_fav_view=False)

        else:
            st.info("Datenbank ist leer.")
    except Exception as e:
        st.error(f"Fehler: {e}")