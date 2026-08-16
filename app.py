import streamlit as st
from supabase import create_client
import pandas as pd
import ast
import yfinance as yf
import altair as alt
import datetime
import pytz

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
    if not tickers:
        return stats
    data = yf.download(tickers, period="1mo", interval="1d", progress=False)['Close']
    
    for ticker in tickers:
        try:
            if isinstance(data, pd.DataFrame) and ticker in data.columns:
                series = data[ticker].dropna()
            elif isinstance(data, pd.Series):
                series = data.dropna()
            else:
                stats[ticker] = None
                continue
                
            if len(series) >= 20:
                ema20 = series.ewm(span=20, adjust=False).mean().iloc[-1]
                current_price = series.iloc[-1]
                dist_pct = ((current_price - ema20) / ema20) * 100
                stats[ticker] = float(dist_pct)
            else:
                stats[ticker] = None
        except Exception:
            stats[ticker] = None
    return stats

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

# --- HAUPTPROGRAMM ---
if check_password():
    st.title("📊 Ticker-Screener Dashboard")

    try:
        response = supabase.table("signals").select("*").execute()
        df_raw = pd.DataFrame(response.data)

        if not df_raw.empty:
            df_raw = df_raw.sort_values('created_at', ascending=True)
            df_raw = df_raw.drop_duplicates(subset=['ticker', 'signal_type'], keep='last')

            if 'signal' in df_raw.columns: df_raw = df_raw.rename(columns={'signal': 'signal_type'})
            if 'meta_data' in df_raw.columns:
                df_raw['meta_data'] = df_raw['meta_data'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else {})
                meta_df = pd.json_normalize(df_raw['meta_data'])
                df_raw = pd.concat([df_raw.drop('meta_data', axis=1), meta_df], axis=1)

            if 'gettex_ticker' in df_raw.columns:
                df_raw['TV_Link'] = df_raw['gettex_ticker'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else "")
            
            df_raw['entry_price'] = pd.to_numeric(df_raw['entry_price'], errors='coerce')
            unique_tickers = df_raw['ticker'].unique().tolist()
            
            with st.spinner("Lade Marktdaten..."):
                price_map = get_all_prices(unique_tickers)
                ema_dist_map = get_ema_stats_bulk(unique_tickers)
            
            df_raw['current_price'] = df_raw['ticker'].map(price_map)
            df_raw['Performance (%)'] = ((df_raw['current_price'] - df_raw['entry_price']) / df_raw['entry_price']) * 100
            df_raw['EMA20_Dist_%'] = df_raw['ticker'].map(ema_dist_map)

            if 'status' not in df_raw.columns:
                df_raw['status'] = 'signal'

            # 1. Sektoren-Chart (Filter < 3% Performance)
            df_signals_only = df_raw[df_raw['status'] == 'signal'].copy()
            df_filtered_chart = df_signals_only[df_signals_only['Performance (%)'] < 3.0]
            
            st.subheader("🏢 Signale nach Sektor (< 3% Performance)")
            if not df_filtered_chart.empty and 'sector' in df_filtered_chart.columns:
                sector_counts = df_filtered_chart['sector'].value_counts().reset_index()
                sector_counts.columns = ['Sektor', 'Anzahl']
                chart = alt.Chart(sector_counts).mark_bar(color='#3b82f6', size=20).encode(
                    x=alt.X('Anzahl:Q', title='Anzahl'),
                    y=alt.Y('Sektor:N', sort='-x', title=None),
                    tooltip=['Sektor', 'Anzahl']
                ).properties(height=max(len(sector_counts) * 35, 100), width=600)
                st.altair_chart(chart)
            else:
                st.write("Keine Signale gefunden, die weniger als 3% gestiegen sind.")

            # 2. Performance Check
            st.divider()
            st.subheader("📈 Performance-Check (Aktive Signale)")
            if not df_signals_only.empty and 'EMA20_Dist_%' in df_signals_only.columns:
                df_u = df_signals_only[df_signals_only['EMA20_Dist_%'] >= 0]
                df_o = df_signals_only[df_signals_only['EMA20_Dist_%'] < 0]
                col1, col2 = st.columns(2)
                col1.metric("Ø Performance (Über EMA20)", f"{df_u['Performance (%)'].mean():.2f}%" if not df_u.empty else "0%")
                col2.metric("Ø Performance (Unter EMA20)", f"{df_o['Performance (%)'].mean():.2f}%" if not df_o.empty else "0%")

            st.divider()
            st.subheader("📋 Signal-Listen & Favoriten")
            
            tab_favs, tab_ueber, tab_unter = st.tabs(["⭐ Favoriten", "🚀 Über EMA20 (Trend)", "⚠️ Unter EMA20 (Dip/Reversal)"])
            
            def render_list(df_subset, button_text, action_type, key_prefix):
                if df_subset.empty:
                    st.info("Keine Einträge.")
                    return
                for _, row in df_subset.iterrows():
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
                        c1.write(f"**{row['ticker']}**\n\n{row.get('company_name', '')}")
                        c2.write(f"**Perf:** {row['Performance (%)']:.2f}%\n\n**Zeit:** {row['candle_time'][:16].replace('T', ' ')}")
                        c3.write(f"**Einstieg:** {row['entry_price']} €\n\n**Sektor:** {row.get('sector', 'N/A')}")
                        if row.get('TV_Link'): c3.markdown(f"[TradingView]({row['TV_Link']})")
                        
                        if c4.button(button_text, key=f"{key_prefix}_{row['id']}"):
                            if action_type == "to_fav":
                                supabase.table("signals").update({"status": "favorite"}).eq("id", row['id']).execute()
                            else:
                                supabase.table("signals").delete().eq("id", row['id']).execute()
                            st.rerun()

            with tab_favs:
                render_list(df_raw[df_raw['status'] == 'favorite'], "🗑️ Entfernen", "remove", "fav")
            with tab_ueber:
                render_list(df_raw[(df_raw['status'] == 'signal') & (df_raw['EMA20_Dist_%'] >= 0)], "⭐ Zu Favoriten", "to_fav", "ueb")
            with tab_unter:
                render_list(df_raw[(df_raw['status'] == 'signal') & (df_raw['EMA20_Dist_%'] < 0)], "⭐ Zu Favoriten", "to_fav", "unt")

        else:
            st.info("Tabelle 'signals' ist leer.")
            
    except Exception as e:
        st.error(f"Fehler: {e}")