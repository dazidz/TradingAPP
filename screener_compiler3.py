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

# Hilfsfunktion zur Ermittlung des historischen EMA20-Status
@st.cache_data(ttl=1800)
def get_historical_ema_status_bulk(tickers_dates):
    results = {}
    ticker_dict = {}
    for t, dt_str in tickers_dates:
        if not t or not dt_str: continue
        try:
            dt = pd.to_datetime(dt_str)
            ticker_dict.setdefault(t, []).append(dt)
        except:
            continue

    for ticker, dates in ticker_dict.items():
        try:
            df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True)
            if df.empty or len(df) < 20:
                continue
            if isinstance(df.columns, pd.MultiIndex): 
                df.columns = df.columns.get_level_values(0)
            df.columns = [str(c).lower() for c in df.columns]
            
            if 'close' not in df.columns: continue
            
            close_s = df['close']
            if isinstance(close_s, pd.DataFrame): close_s = close_s.iloc[:, 0]
            
            ema20_s = close_s.ewm(span=20, adjust=False).mean()
            
            for dt in dates:
                sub = close_s.loc[:dt]
                if not sub.empty:
                    idx = sub.index[-1]
                    price = float(close_s.loc[idx])
                    ema = float(ema20_s.loc[idx])
                    results[(ticker, str(dt))] = (price >= ema)
        except Exception:
            continue
    return results

# --- SCREENER LOGIK ---
try:
    response = supabase.table("signals").select("*").execute()
    df = pd.DataFrame(response.data)

    history_response = supabase.table("signal_history").select("*").order("closed_at", desc=True).execute()
    hist_df = pd.DataFrame(history_response.data)

    fav_response = supabase.table("favorites").select("ticker").execute()
    fav_tickers = [row['ticker'] for row in fav_response.data] if fav_response.data else []

    if not df.empty:
        if 'candle_time' in df.columns:
            df = df.sort_values(by='candle_time', ascending=False).drop_duplicates(subset=['ticker'], keep='first').reset_index(drop=True)
        else:
            df = df.drop_duplicates(subset=['ticker'], keep='first').reset_index(drop=True)
        
        if 'meta_data' in df.columns:
            df['meta_data'] = df['meta_data'].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) and x.startswith('{') else (x if isinstance(x, dict) else {})
            )
            meta_df = pd.json_normalize(df['meta_data'])
            df = pd.concat([df.drop(columns=['meta_data']), meta_df], axis=1)

        for col in ['gettex_ticker', 'entry_price', 'sector', 'company_name', 'candle_time', 'ticker']:
            if col not in df.columns: df[col] = ""

        df['is_favorite'] = df['ticker'].isin(fav_tickers)
        df['Chart'] = df['gettex_ticker'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else "")
        
        unique_tickers = [t for t in df['ticker'].unique().tolist() if t]
        prices, exchanges = get_stock_meta(unique_tickers)
        ema_stats = get_ema_stats_bulk(unique_tickers)
        
        df['current_price'] = df['ticker'].map(prices)
        df['exchange'] = df['ticker'].map(exchanges)
        
        df['entry_price_num'] = pd.to_numeric(df['entry_price'], errors='coerce')
        df['Performance (%)'] = ((df['current_price'] - df['entry_price_num']) / df['entry_price_num']) * 100
        df['EMA20_Dist_%'] = df['ticker'].map(ema_stats)

        total_count_global = len(df)
        sector_counts_global = df.groupby('sector').size()
        sector_share_global = (sector_counts_global / total_count_global) * 100

        tab_favs, tab_ueber, tab_unter, tab_gesamt, tab_historie = st.tabs(["⭐ Favoriten", "EMA20 🟢", "EMA20 🔴", "📁 Gesamtliste", "📜 Historie"])

        def show_table(df_subset, is_fav_view=False, is_total_view=False):
            d = df_subset.copy()
            if d.empty:
                st.info("Keine Daten für diese Filtereinstellung vorhanden.")
                return

            d['Action'] = False
            
            if is_total_view:
                d['⭐'] = d['is_favorite'].apply(lambda x: "⭐" if x else "")
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
                "Action": st.column_config.CheckboxColumn("Entfernen" if is_fav_view else "Favorit", default=False)
            }
            
            existing_cols = [c for c in cols if c in d.columns]
            
            if 'sector' in d.columns and 'Performance (%)' in d.columns:
                chart_data = d[(d['Performance (%)'] < 3.0) & (d['Performance (%)'].notnull())]
                if not chart_data.empty and 'sector' in chart_data.columns:
                    total_subset_count = len(chart_data)
                    sector_counts_subset = chart_data.groupby('sector').size()
                    sector_share_subset = (sector_counts_subset / total_subset_count) * 100
                    
                    sector_df = pd.DataFrame({
                        'Anteil_Signale': sector_share_subset,
                        'Anteil_Watchlist': sector_share_global,
                        'Treffer': sector_counts_subset,
                        'Gesamt_WL': sector_counts_global
                    }).dropna()
                    
                    sector_df['Score'] = sector_df['Treffer'] * (
                        (sector_df['Anteil_Signale'] + 1) / (sector_df['Anteil_Watchlist'] + 1)
                    )
                    
                    sector_df = sector_df.reset_index().sort_values(by='Score', ascending=False).head(10)
                    
                    if not sector_df.empty:
                        c = alt.Chart(sector_df).mark_bar(color='#3b82f6').encode(
                            x=alt.X('Score:Q', title='Sektor-Score (Treffer & Gewichtung kombiniert)', axis=alt.Axis(format='.1f')),
                            y=alt.Y('sector:N', sort='-x', title='Sektor'),
                            tooltip=[
                                'sector', 
                                alt.Tooltip('Score:Q', format='.2f', title='Score'),
                                alt.Tooltip('Anteil_Signale:Q', format='.1f', title='Anteil Signale (%)'),
                                alt.Tooltip('Anteil_Watchlist:Q', format='.1f', title='Anteil Watchlist (%)'),
                                'Treffer', 
                                'Gesamt_WL'
                            ]
                        ).properties(height=250)
                        st.altair_chart(c, use_container_width=True)

            if 'Performance (%)' in d.columns and not d['Performance (%)'].dropna().empty:
                avg_perf = d['Performance (%)'].mean()
                st.metric("Ø Performance der Liste", f"{avg_perf:.2f}%")

            edited = st.data_editor(d[existing_cols], column_config=conf, hide_index=True, use_container_width=True)
            
            changed_rows = edited[edited['Action'] == True]
            if not changed_rows.empty:
                for _, row in changed_rows.iterrows():
                    t_symbol = df_subset.loc[df_subset['company_name'] == row['company_name'], 'ticker'].values[0]
                    if is_fav_view:
                        supabase.table("favorites").delete().eq("ticker", t_symbol).execute()
                    else:
                        supabase.table("favorites").upsert({"ticker": t_symbol}, on_conflict="ticker").execute()
                st.rerun()

        with tab_favs: show_table(df[df['is_favorite'] == True], is_fav_view=True)
        with tab_ueber: show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'].fillna(-1) >= 0)])
        with tab_unter: show_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'].fillna(0) < 0)])
        with tab_gesamt: show_table(df, is_total_view=True)

        # --- TAB: HISTORIE & PERFORMANCE ---
        with tab_historie:
            st.subheader("📜 Abgeschlossene Signale & Performance-Historie")
            
            if hist_df.empty:
                st.info("Noch keine archivierten Signale in der Historie vorhanden.")
            else:
                pairs = [(row.get('ticker'), row.get('candle_time')) for _, row in hist_df.iterrows()]
                ema_status_map = get_historical_ema_status_bulk(pairs)
                
                hist_df['above_ema20'] = hist_df.apply(lambda r: ema_status_map.get((r.get('ticker'), str(r.get('candle_time'))), False), axis=1)
                hist_df['is_favorite'] = hist_df['ticker'].isin(fav_tickers)

                total_trades = len(hist_df)
                avg_perf_hist = hist_df['performance_pct'].mean() if 'performance_pct' in hist_df.columns else 0.0
                win_trades = len(hist_df[hist_df['performance_pct'] > 0])
                win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0.0
                
                # Favoriten-Metriken für die Top-Metrik-Karten vorbereiten
                sub_favs_hist = hist_df[hist_df['is_favorite'] == True]
                fav_count = len(sub_favs_hist)
                fav_avg_perf = sub_favs_hist['performance_pct'].mean() if fav_count > 0 and 'performance_pct' in sub_favs_hist.columns else 0.0

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Abgeschlossene Trades", total_trades)
                col2.metric("Ø Performance (Gesamt)", f"{avg_perf_hist:.2f}%")
                col3.metric("Ø Performance (⭐ Favs)", f"{fav_avg_perf:.2f}%", f"{fav_count} Trades")
                col4.metric("Win-Rate (Gesamt)", f"{win_rate:.1f}%")
                
                st.markdown("---")
                st.subheader("🎯 Erweiterte Performance-Auswertungen")

                # Sub-Gruppen berechnen
                sub_above_ema = hist_df[hist_df['above_ema20'] == True]
                sub_below_ema = hist_df[hist_df['above_ema20'] == False]
                sub_elite = hist_df[hist_df['signal_type'] == 'ELITE']
                sub_no_elite = hist_df[hist_df['signal_type'] != 'ELITE']
                sub_above_ema_and_elite = hist_df[(hist_df['above_ema20'] == True) & (hist_df['signal_type'] == 'ELITE')]
                sub_below_ema_and_no_elite = hist_df[(hist_df['above_ema20'] == False) & (hist_df['signal_type'] != 'ELITE')]

                def get_metrics_dict(sub_df, name):
                    count = len(sub_df)
                    perf = sub_df['performance_pct'].mean() if count > 0 and 'performance_pct' in sub_df.columns else 0.0
                    w_count = len(sub_df[sub_df['performance_pct'] > 0]) if count > 0 else 0
                    w_rate = (w_count / count) * 100 if count > 0 else 0.0
                    return {
                        "Kategorie": name,
                        "Anzahl Trades": count,
                        "Ø Performance": f"{perf:.2f}%",
                        "Win-Rate": f"{w_rate:.1f}%"
                    }

                eval_data = [
                    get_metrics_dict(sub_favs_hist, "⭐ Nur Favoriten"),
                    get_metrics_dict(sub_above_ema, "Über EMA20 (Gesamt)"),
                    get_metrics_dict(sub_below_ema, "Unter EMA20 (Gesamt)"),
                    get_metrics_dict(sub_elite, "Elite Signale (Gesamt)"),
                    get_metrics_dict(sub_no_elite, "Ohne Elite Signale (Kaufen)"),
                    get_metrics_dict(sub_above_ema_and_elite, "Über EMA20 & Elite"),
                    get_metrics_dict(sub_below_ema_and_no_elite, "Unter EMA20 & Ohne Elite")
                ]
                
                eval_df = pd.DataFrame(eval_data)
                st.dataframe(eval_df, hide_index=True, use_container_width=True)

                st.markdown("---")
                
                hist_cols = ['company_name', 'ticker', 'signal_type', 'sector', 'candle_time', 'entry_price', 'exit_price', 'performance_pct', 'exit_reason', 'closed_at']
                existing_hist_cols = [c for c in hist_cols if c in hist_df.columns]
                
                hist_conf = {
                    "company_name": st.column_config.TextColumn("Firma", disabled=True),
                    "ticker": st.column_config.TextColumn("Ticker", disabled=True),
                    "signal_type": st.column_config.TextColumn("Signal", disabled=True),
                    "sector": st.column_config.TextColumn("Sektor", disabled=True),
                    "candle_time": st.column_config.TextColumn("Candle Time", disabled=True),
                    "entry_price": st.column_config.NumberColumn("Entry", format="€%.2f"),
                    "exit_price": st.column_config.NumberColumn("Exit", format="€%.2f"),
                    "performance_pct": st.column_config.NumberColumn("Performance", format="%.2f%%"),
                    "exit_reason": st.column_config.TextColumn("Grund", disabled=True),
                    "closed_at": st.column_config.TextColumn("Geschlossen am", disabled=True)
                }
                
                st.dataframe(hist_df[existing_hist_cols], column_config=hist_conf, hide_index=True, use_container_width=True)

    else:
        st.info("Keine Daten in der Supabase-Datenbank vorhanden.")

except Exception as e:
    st.error(f"Fehler: {e}")