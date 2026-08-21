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

# Caching für Daten & Exchange-Informationen
@st.cache_data(ttl=1800)
def get_stock_meta(tickers):
    prices = {}
    exchanges = {}
    if not tickers: return prices, exchanges
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1d")
            if not hist.empty: 
                prices[ticker] = float(hist['Close'].iloc[-1])
            
            info = t.info
            exchanges[ticker] = info.get('exchange', 'N/A')
        except Exception: 
            continue
    return prices, exchanges

@st.cache_data(ttl=1800)
def get_ema_stats_bulk(tickers):
    stats = {}
    if not tickers: return stats
    try:
        data = yf.download(tickers, period="1mo", interval="1d", progress=False)
        if 'Close' in data:
            data = data['Close']
        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) >= 20:
                    ema20 = series.ewm(span=20, adjust=False).mean().iloc[-1]
                    stats[ticker] = float(((series.iloc[-1] - ema20) / ema20) * 100)
            except Exception: stats[ticker] = None
    except Exception: pass
    return stats

# --- SCREENER LOGIK ---
try:
    response = supabase.table("signals").select("*").execute()
    df = pd.DataFrame(response.data)

    if not df.empty:
        if 'status' not in df.columns: df['status'] = 'signal'
        df = df.drop_duplicates(subset=['ticker', 'signal_type', 'status'], keep='last').reset_index(drop=True)
        
        if 'meta_data' in df.columns:
            df['meta_data'] = df['meta_data'].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) and x.startswith('{') else (x if isinstance(x, dict) else {})
            )
            meta_df = pd.json_normalize(df['meta_data'])
            df = pd.concat([df.drop(columns=['meta_data']), meta_df], axis=1)

        for col in ['gettex_ticker', 'entry_price', 'sector', 'company_name', 'candle_time', 'ticker']:
            if col not in df.columns: df[col] = ""

        df['Chart'] = df['gettex_ticker'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else "")
        
        unique_tickers = [t for t in df['ticker'].unique().tolist() if t]
        prices, exchanges = get_stock_meta(unique_tickers)
        ema_stats = get_ema_stats_bulk(unique_tickers)
        
        df['current_price'] = df['ticker'].map(prices)
        df['exchange'] = df['ticker'].map(exchanges)
        
        df['entry_price_num'] = pd.to_numeric(df['entry_price'], errors='coerce')
        df['Performance (%)'] = ((df['current_price'] - df['entry_price_num']) / df['entry_price_num']) * 100
        df['EMA20_Dist_%'] = df['ticker'].map(ema_stats)

        # Gesamtzahl pro Sektor über die GESAMTE Datenbank/Watchlist (unabhängig vom Tab)
        total_per_sector_global = df.groupby('sector').size()

        tab_favs, tab_ueber, tab_unter, tab_gesamt = st.tabs(["⭐ Favoriten", "EMA20 🟢", "EMA20 🔴", "📁 Gesamtliste"])

        def show_table(df_subset, is_fav_view=False, is_total_view=False):
            d = df_subset.copy()
            if d.empty:
                st.info("Keine Daten für diese Filtereinstellung vorhanden.")
                return

            d['Action'] = False
            
            if is_total_view:
                d['⭐'] = d['status'].apply(lambda x: "⭐" if x == 'favorite' else "")
                cols = ['⭐', 'Action', 'company_name', 'Chart', 'Performance (%)', 'candle_time', 'sector', 'exchange', 'entry_price', 'gettex_ticker']
            else:
                cols = ['Action', 'company_name', 'Chart', 'Performance (%)', 'candle_time', 'sector', 'exchange', 'entry_price', 'gettex_ticker']

            conf = {
                "⭐": st.column_config.TextColumn("⭐", width="small"),
                "company_name": st.column_config.TextColumn("Firma", disabled=True),
                "Chart": st.column_config.LinkColumn("Link", display_text="📈 Öffnen"),
                "Performance (%)": st.column_config.NumberColumn("Performance", format="%.2f%%"),
                "candle_time": st.column_config.TextColumn("Candle Time"),
                "sector": st.column_config.TextColumn("Sektor", disabled=True),
                "exchange": st.column_config.TextColumn("Börse", disabled=True),
                "entry_price": st.column_config.NumberColumn("Entry", format="€%.2f"),
                "gettex_ticker": st.column_config.TextColumn("Gettex Ticker", disabled=True),
                "Action": st.column_config.CheckboxColumn("Favorit" if not is_fav_view else "Entfernen", default=False)
            }
            
            existing_cols = [c for c in cols if c in d.columns]
            
            # --- DIAGRAMM MIT GLOBALER SEKTOR-BASIS ---
            if 'sector' in d.columns and 'Performance (%)' in d.columns:
                chart_data = d[(d['Performance (%)'] < 3.0) & (d['Performance (%)'].notnull())]
                if not chart_data.empty and 'sector' in chart_data.columns:
                    filtered_per_sector = chart_data.groupby('sector').size()
                    
                    # Nutzung von total_per_sector_global statt nur der Teilliste
                    sector_df = pd.DataFrame({'Gesamt': total_per_sector_global, 'Treffer': filtered_per_sector}).dropna()
                    sector_df['Anteil_%'] = (sector_df['Treffer'] / sector_df['Gesamt']) * 100
                    sector_df = sector_df.reset_index().sort_values(by='Anteil_%', ascending=False).head(10)
                    
                    if not sector_df.empty:
                        c = alt.Chart(sector_df).mark_bar(color='#3b82f6').encode(
                            x=alt.X('Anteil_%:Q', title='Anteil der Signale an der Gesamt-Watchlist (%)', axis=alt.Axis(tickMinStep=1)),
                            y=alt.Y('sector:N', sort='-x', title='Sektor'),
                            tooltip=['sector', alt.Tooltip('Anteil_%:Q', format='.1f', title='Anteil (%)'), 'Treffer', 'Gesamt']
                        ).properties(height=250)
                        st.altair_chart(c, use_container_width=True)

            if 'Performance (%)' in d.columns and not d['Performance (%)'].dropna().empty:
                avg_perf = d['Performance (%)'].mean()
                st.metric("Ø Performance der Liste", f"{avg_perf:.2f}%")

            edited = st.data_editor(d[existing_cols], column_config=conf, hide_index=True, use_container_width=True)
            
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
        with tab_ueber: show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'].fillna(-1) >= 0)])
        with tab_unter: show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'].fillna(0) < 0)])
        with tab_gesamt: show_table(df, is_total_view=True)

    else:
        st.info("Keine Daten in der Supabase-Datenbank vorhanden.")

except Exception as e:
    st.error(f"Fehler: {e}")