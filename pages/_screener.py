import streamlit as st
from supabase import create_client
import pandas as pd
import ast
import yfinance as yf
import altair as alt

# Passwort-Schutz
if "password_correct" not in st.session_state or not st.session_state.password_correct:
    st.error("Bitte zuerst auf der Startseite anmelden!")
    st.stop()

st.title("📊 Ticker-Screener")

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# Caching für Daten
@st.cache_data(ttl=1800)
def get_all_prices(tickers):
    prices = {}
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="1d")
            if not hist.empty: prices[ticker] = float(hist['Close'].iloc[-1])
        except: continue
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
        except: stats[ticker] = None
    return stats

# --- SCREENER LOGIK ---
try:
    response = supabase.table("signals").select("*").execute()
    df = pd.DataFrame(response.data)

    if not df.empty:
        if 'status' not in df.columns: df['status'] = 'signal'
        df = df.drop_duplicates(subset=['ticker', 'signal_type', 'status'], keep='last')
        
        if 'meta_data' in df.columns:
            df['meta_data'] = df['meta_data'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else {})
            df = pd.concat([df.drop('meta_data', axis=1), pd.json_normalize(df['meta_data'])], axis=1)

        df['Chart'] = df['gettex_ticker'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x}")
        df['current_price'] = df['ticker'].map(get_all_prices(df['ticker'].unique().tolist()))
        df['Performance (%)'] = ((df['current_price'] - df['entry_price'].astype(float)) / df['entry_price'].astype(float)) * 100
        df['EMA20_Dist_%'] = df['ticker'].map(get_ema_stats_bulk(df['ticker'].unique().tolist()))

        tab_favs, tab_ueber, tab_unter, tab_gesamt = st.tabs(["⭐ Favoriten", "EMA20 🟢", "EMA20 🔴", "📁 Gesamtliste"])

        def show_table(df_subset, is_fav_view=False, is_total_view=False):
            d = df_subset.copy()
            d['Action'] = False
            
            if is_total_view:
                # Füge für die Gesamtliste ganz vorne die Stern-Spalte ein
                d['⭐'] = d['status'].apply(lambda x: "⭐" if x == 'favorite' else "")
                cols = ['⭐', 'Action', 'company_name', 'Chart', 'sector', 'Performance (%)', 'entry_price']
            else:
                cols = ['Action', 'company_name', 'Chart', 'sector', 'Performance (%)', 'entry_price']

            conf = {
                "⭐": st.column_config.TextColumn("⭐", width="small"),
                "company_name": st.column_config.TextColumn("Firma", disabled=True),
                "Chart": st.column_config.LinkColumn("TradingView", display_text="📈 Öffnen"),
                "Performance (%)": st.column_config.NumberColumn(format="%.2f%%"),
                "Action": st.column_config.CheckboxColumn("Favorit" if not is_fav_view else "Entfernen", default=False)
            }
            
            existing_cols = [c for c in cols if c in d.columns]
            edited = st.data_editor(d[existing_cols], column_config=conf, hide_index=True, use_container_width=True)
            
            changed = edited[edited['Action'] == True]
            if not changed.empty:
                for _, row in edited[edited['Action'] == True].iterrows():
                    # Finde das passende ID-Feld über den Chart-Link oder Firmennamen
                    target_id = df_subset[df_subset['company_name'] == row['company_name']]['id'].iloc[0]
                    if is_fav_view: 
                        supabase.table("signals").delete().eq("id", target_id).execute()
                    else: 
                        supabase.table("signals").update({"status": "favorite"}).eq("id", target_id).execute()
                    st.rerun()

        with tab_favs: show_table(df[df['status'] == 'favorite'], is_fav_view=True)
        with tab_ueber: show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] >= 0)])
        with tab_unter: show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] < 0)])
        with tab_gesamt: show_table(df, is_total_view=True)
except Exception as e: st.error(f"Fehler: {e}")