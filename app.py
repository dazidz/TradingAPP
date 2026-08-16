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
        # Daten abrufen (Wir laden alle, um sowohl Signale als auch Favoriten zu haben)
        response = supabase.table("signals").select("*").execute()
        df_raw = pd.DataFrame(response.data)

        if not df_raw.empty:
            # 1. Dubletten bereinigen
            df_raw = df_raw.sort_values('created_at', ascending=True)
            df_raw = df_raw.drop_duplicates(subset=['ticker', 'signal_type'], keep='last')

            # 2. Spalten-Mapping & Metadaten
            if 'signal' in df_raw.columns: df_raw = df_raw.rename(columns={'signal': 'signal_type'})
            if 'meta_data' in df_raw.columns:
                df_raw['meta_data'] = df_raw['meta_data'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else {})
                meta_df = pd.json_normalize(df_raw['meta_data'])
                df_raw = pd.concat([df_raw.drop('meta_data', axis=1), meta_df], axis=1)

            if 'gettex_ticker' in df_raw.columns:
                df_raw['TV_Link'] = df_raw['gettex_ticker'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else "")
            
            # 3. Performance & Kurse für ALLE geladenen Ticker berechnen
            df_raw['entry_price'] = pd.to_numeric(df_raw['entry_price'], errors='coerce')
            unique_tickers = df_raw['ticker'].unique().tolist()
            
            with st.spinner("Lade Marktdaten..."):
                price_map = get_all_prices(unique_tickers)
                ema_dist_map = get_ema_stats_bulk(unique_tickers)
            
            df_raw['current_price'] = df_raw['ticker'].map(price_map)
            df_raw['Performance (%)'] = ((df_raw['current_price'] - df_raw['entry_price']) / df_raw['entry_price']) * 100
            df_raw['EMA20_Dist_%'] = df_raw['ticker'].map(ema_dist_map)

            # Fallback für status, falls Spalte neu ist
            if 'status' not in df_raw.columns:
                df_raw['status'] = 'signal'

            # --- 4. Sektoren-Visualisierung (Nur aktive Signale) ---
            df_signals_only = df_raw[df_raw['status'] == 'signal']
            
            st.subheader("🏢 Signale nach Sektor (Aktive Signale)")
            if not df_signals_only.empty and 'sector' in df_signals_only.columns:
                sector_counts = df_signals_only['sector'].value_counts().reset_index()
                sector_counts.columns = ['Sektor', 'Anzahl']
                
                chart_height = max(len(sector_counts) * 35, 100)
                
                chart = alt.Chart(sector_counts).mark_bar(
                    color='#3b82f6',
                    size=20
                ).encode(
                    x=alt.X('Anzahl:Q', title='Anzahl'),
                    y=alt.Y('Sektor:N', sort='-x', title=None),
                    tooltip=['Sektor', 'Anzahl']
                ).properties(
                    height=chart_height,
                    width=600 
                ).configure_axis(
                    labelLimit=300 
                )
                
                with st.container():
                    st.altair_chart(chart)
            else:
                st.write("Keine Sektoren-Daten für aktive Signale.")
            
            # --- 5. EMA Performance Check ---
            st.divider()
            st.subheader("📈 Performance-Check: Filter-Effizienz (Aktive Signale)")
            
            if not df_signals_only.empty and 'EMA20_Dist_%' in df_signals_only.columns:
                df_ueber_perf = df_signals_only[df_signals_only['EMA20_Dist_%'] >= 0]
                df_unter_perf = df_signals_only[df_signals_only['EMA20_Dist_%'] < 0]
                
                col1, col2 = st.columns(2)
                
                avg_ueber = df_ueber_perf['Performance (%)'].mean() if not df_ueber_perf.empty else 0
                avg_unter = df_unter_perf['Performance (%)'].mean() if not df_unter_perf.empty else 0
                
                with col1:
                    st.metric(label="Ø Performance (Über EMA20)", value=f"{avg_ueber:.2f}%", delta=f"{avg_ueber - avg_unter:.2f}% vs. Unter EMA")
                with col2:
                    st.metric(label="Ø Performance (Unter EMA20)", value=f"{avg_unter:.2f}%")
                st.caption(f"Anzahl Signale über EMA: {len(df_ueber_perf)} | Anzahl unter EMA: {len(df_unter_perf)}")

            st.divider()

            # --- 6. Signal-Listen & Favoriten ---
            st.subheader("📋 Signal-Listen & Favoriten")
            
            # Tabs: Favoriten + Über EMA20 + Unter EMA20
            tab_favs, tab_ueber, tab_unter = st.tabs(["⭐ Favoriten", "🚀 Über EMA20 (Trend)", "⚠️ Unter EMA20 (Dip/Reversal)"])
            
            # DataFrames filtern
            df_favs = df_raw[df_raw['status'] == 'favorite'].copy()
            df_ueber = df_raw[(df_raw['status'] == 'signal') & (df_raw['EMA20_Dist_%'] >= 0)].copy()
            df_unter = df_raw[(df_raw['status'] == 'signal') & (df_raw['EMA20_Dist_%'] < 0)].copy()
            
            cols_to_show = ['company_name', 'ticker', 'sector', 'signal_type', 'Performance (%)', 'EMA20_Dist_%', 'entry_price', 'candle_time', 'TV_Link']
            existing_cols = [c for c in cols_to_show if c in df_raw.columns]
            
            col_config = {
                "TV_Link": st.column_config.LinkColumn("TradingView", display_text="Analyse"),
                "Performance (%)": st.column_config.NumberColumn("Performance (%)", format="%.2f%%"),
                "EMA20_Dist_%": st.column_config.NumberColumn("EMA20 Dist. %", format="%.2f%%"),
                "entry_price": st.column_config.NumberColumn("Einstieg", format="%.2f €")
            }

            # --- TAB 1: FAVORITEN ---
            with tab_favs:
                if not df_favs.empty:
                    st.info("Hier sind deine handverlesenen Favoriten. Klicke auf 'Entfernen', wenn du eingestiegen bist oder sie verwirfst.")
                    for _, row in df_favs.iterrows():
                        with st.container(border=True):
                            c1, c2, c3, c4 = st.columns([3, 3, 3, 2])
                            c1.write(f"**{row['ticker']}** - {row.get('company_name', '')}")
                            c2.write(f"Typ: {row['signal_type']} | Einstieg: {row['entry_price']} €")
                            c3.write(f"Sektor: {row.get('sector', 'N/A')}")
                            if row.get('TV_Link'):
                                c3.markdown(f"[TradingView Chart]({row['TV_Link']})")
                            
                            if c4.button("🗑️ Entfernen", key=f"remove_fav_{row['id']}"):
                                supabase.table("signals").delete().eq("id", row['id']).execute()
                                st.success(f"{row['ticker']} aus Favoriten gelöscht!")
                                st.rerun()
                else:
                    st.info("Noch keine Favoriten ausgewählt. Verschiebe spannende Signale aus den anderen Tabs hierher.")

            # --- TAB 2: ÜBER EMA20 ---
            with tab_ueber:
                if not df_ueber.empty:
                    for _, row in df_ueber.iterrows():
                        with st.container(border=True):
                            c1, c2, c3, c4 = st.columns([3, 3, 3, 2])
                            c1.write(f"**{row['ticker']}** - {row.get('company_name', '')}")
                            c2.write(f"Typ: {row['signal_type']} | Einstieg: {row['entry_price']} €")
                            c3.write(f"Sektor: {row.get('sector', 'N/A')}")
                            if row.get('TV_Link'):
                                c3.markdown(f"[TradingView Chart]({row['TV_Link']})")
                            
                            if c4.button("⭐ Zu Favoriten", key=f"to_fav_u_{row['id']}"):
                                supabase.table("signals").update({"status": "favorite"}).eq("id", row['id']).execute()
                                st.success(f"{row['ticker']} zu Favoriten verschoben!")
                                st.rerun()
                else:
                    st.info("Aktuell keine Signale über dem EMA20.")

            # --- TAB 3: UNTER EMA20 ---
            with tab_unter:
                if not df_unter.empty:
                    for _, row in df_unter.iterrows():
                        with st.container(border=True):
                            c1, c2, c3, c4 = st.columns([3, 3, 3, 2])
                            c1.write(f"**{row['ticker']}** - {row.get('company_name', '')}")
                            c2.write(f"Typ: {row['signal_type']} | Einstieg: {row['entry_price']} €")
                            c3.write(f"Sektor: {row.get('sector', 'N/A')}")
                            if row.get('TV_Link'):
                                c3.markdown(f"[TradingView Chart]({row['TV_Link']})")
                            
                            if c4.button("⭐ Zu Favoriten", key=f"to_fav_d_{row['id']}"):
                                supabase.table("signals").update({"status": "favorite"}).eq("id", row['id']).execute()
                                st.success(f"{row['ticker']} zu Favoriten verschoben!")
                                st.rerun()
                else:
                    st.info("Aktuell keine Signale unter dem EMA20.")

        else:
            st.info("Tabelle 'signals' ist leer.")
            
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")