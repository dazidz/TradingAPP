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
            if 'status' not in df.columns: df['status'] = 'signal'
            df = df.drop_duplicates(subset=['ticker', 'signal_type', 'status'], keep='last')
            
            if 'meta_data' in df.columns:
                df['meta_data'] = df['meta_data'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else {})
                df = pd.concat([df.drop('meta_data', axis=1), pd.json_normalize(df['meta_data'])], axis=1)

            df['tv_url'] = df['gettex_ticker'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x}")
            df['current_price'] = df['ticker'].map(get_all_prices(df['ticker'].unique().tolist()))
            df['Performance (%)'] = ((df['current_price'] - df['entry_price'].astype(float)) / df['entry_price'].astype(float)) * 100
            df['EMA20_Dist_%'] = df['ticker'].map(get_ema_stats_bulk(df['ticker'].unique().tolist()))

            # Chart
            df_chart = df[df['Performance (%)'] < 3.0].copy()
            st.subheader("🏢 Signale nach Sektor")
            if not df_chart.empty:
                chart_data = df_chart['sector'].value_counts().reset_index()
                chart_data.columns = ['Sektor', 'Anzahl']
                chart = alt.Chart(chart_data).mark_bar(color='#3b82f6').encode(
                    x='Anzahl:Q', y=alt.Y('Sektor:N', sort='-x')).properties(height=200).configure_view(stroke=None)
                st.altair_chart(chart, use_container_width=True)

            st.divider()
            tab_favs, tab_ueber, tab_unter, tab_gesamt = st.tabs(["⭐ Favoriten", "🚀 Trend", "⚠️ Dip", "📁 Gesamtliste"])

            def show_table(df_subset, is_fav_view=False, is_total_view=False):
                d = df_subset.copy()
                if is_total_view:
                    d['company_name'] = d.apply(lambda x: f"⭐ {x['company_name']}" if x['status'] == 'favorite' else x['company_name'], axis=1)
                
                d['Action'] = False
                
                # Konfiguration: tv_url ist der Link, display_text zeigt den Namen aus der Spalte company_name
                conf = {
                    "tv_url": st.column_config.LinkColumn("Firma", display_text="company_name"),
                    "Performance (%)": st.column_config.NumberColumn(format="%.2f%%"),
                    "Action": st.column_config.CheckboxColumn("Favorit" if not is_fav_view else "Entfernen", default=False)
                }
                
                # Wir zeigen tv_url (als Firma), Action, etc.
                edited = st.data_editor(d[['Action', 'tv_url', 'sector', 'Performance (%)', 'entry_price', 'candle_time']], 
                                        column_config=conf, hide_index=True, use_container_width=True)
                
                changed = edited[edited['Action'] == True]
                if not changed.empty:
                    for _, row in changed.iterrows():
                        target_id = df_subset[df_subset['tv_url'] == row['tv_url']]['id'].iloc[0]
                        if is_fav_view: supabase.table("signals").delete().eq("id", target_id).execute()
                        else: supabase.table("signals").update({"status": "favorite"}).eq("id", target_id).execute()
                        st.rerun()

            with tab_favs: show_table(df[df['status'] == 'favorite'], is_fav_view=True)
            with tab_ueber: show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] >= 0)])
            with tab_unter: show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] < 0)])
            with tab_gesamt: show_table(df, is_total_view=True)
    except Exception as e: st.error(f"Fehler: {e}")