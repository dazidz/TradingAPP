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
                d['⭐'] = d['status'].apply(lambda x: "⭐" if x == 'favorite' else "")
                cols = ['⭐', 'Action', 'company_name', 'Chart', 'sector', 'Performance (%)', 'current_price', 'entry_price', 'candle_time']
            else:
                cols = ['Action', 'company_name', 'Chart', 'sector', 'Performance (%)', 'current_price', 'entry_price', 'candle_time']

            conf = {
                "⭐": st.column_config.TextColumn("⭐", width="small"),
                "company_name": st.column_config.TextColumn("Firma", disabled=True),
                "Chart": st.column_config.LinkColumn("TradingView", display_text="📈 Öffnen"),
                "Performance (%)": st.column_config.NumberColumn(format="%.2f%%"),
                "current_price": st.column_config.NumberColumn("Aktuell", format="€%.2f"),
                "entry_price": st.column_config.NumberColumn("Entry", format="€%.2f"),
                "candle_time": st.column_config.TextColumn("Candle Time"),
                "Action": st.column_config.CheckboxColumn("Favorit" if not is_fav_view else "Entfernen", default=False)
            }
            
            existing_cols = [c for c in cols if c in d.columns]
            
            # 1. Anzeige über die Gesamtperformance aller Aktien in der Liste
            if not d.empty and 'Performance (%)' in d.columns:
                avg_perf = d['Performance (%)'].mean()
                st.metric("Ø Gesamtperformance der Liste", f"{avg_perf:.2f}%")

            # 2. Diagramm: Anzahl Aktien je Sektor (< 3% Performance, Top 10 Sektoren)
            if not d.empty and 'sector' in d.columns and 'Performance (%)' in d.columns:
                chart_data = d[(d['Performance (%)'] < 3) & (d['Performance (%)'].notnull())]
                if not chart_data.empty:
                    sector_counts = chart_data.groupby('sector').size().reset_index(name='Anzahl')
                    sector_counts = sector_counts.sort_values(by='Anzahl', ascending=False).head(10)
                    
                    c = alt.Chart(sector_counts).mark_bar().encode(
                        x=alt.X('Anzahl:Q', title='Anzahl Signale / Aktien (< 3% Perf.)'),
                        y=alt.Y('sector:N', sort='-x', title='Sektor'),
                        tooltip=['sector', 'Anzahl']
                    ).properties(height=250)
                    st.altair_chart(c, use_container_width=True)

            edited = st.data_editor(d[existing_cols], column_config=conf, hide_index=True, use_container_width=True)
            
            # Batch-Update für Favoriten (schnell)
            changed_rows = edited[edited['Action'] == True]
            if not changed_rows.empty:
                changed_names = changed_rows['company_name'].tolist()
                target_ids = df_subset[df_subset['company_name'].isin(changed_names)]['id'].tolist()
                
                if target_ids:
                    if is_fav_view:
                        supabase.table("signals").delete().in_("id", target_ids).execute()
                    else:
                        supabase.table("signals").update({"status": "favorite"}).in_("id", target_ids).execute()
                    st.rerun()

        with tab_favs: show_table(df[df['status'] == 'favorite'], is_fav_view=True)
        with tab_ueber: show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] >= 0)])
        with tab_unter: show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] < 0)])
        with tab_gesamt: show_table(df, is_total_view=True)
except Exception as e: st.error(f"Fehler: {e}")