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
        # Daten abrufen
        response = supabase.table("signals").select("*").execute()
        df = pd.DataFrame(response.data)

        if not df.empty:
            # 1. Dubletten bereinigen (verhindert doppelte Einträge pro Signal)
            df = df.sort_values('created_at', ascending=True)
            df = df.drop_duplicates(subset=['ticker', 'signal_type'], keep='last')

            # 2. Spalten-Mapping & Metadaten
            if 'signal' in df.columns: df = df.rename(columns={'signal': 'signal_type'})
            if 'status' not in df.columns: df['status'] = 'signal'
            
            if 'meta_data' in df.columns:
                df['meta_data'] = df['meta_data'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else {})
                meta_df = pd.json_normalize(df['meta_data'])
                df = pd.concat([df.drop('meta_data', axis=1), meta_df], axis=1)

            if 'gettex_ticker' in df.columns:
                df['TV_Link'] = df['gettex_ticker'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else "")
            
            # 3. Performance & Kurse
            df['entry_price'] = pd.to_numeric(df['entry_price'], errors='coerce')
            unique_tickers = df['ticker'].unique().tolist()
            
            with st.spinner("Lade Marktdaten..."):
                price_map = get_all_prices(unique_tickers)
                ema_dist_map = get_ema_stats_bulk(unique_tickers)
            
            df['current_price'] = df['ticker'].map(price_map)
            df['Performance (%)'] = ((df['current_price'] - df['entry_price']) / df['entry_price']) * 100
            df['EMA20_Dist_%'] = df['ticker'].map(ema_dist_map)
            
            # 4. Sektoren-Visualisierung (Nur Signale mit < 3% Performance)
            df_chart_filtered = df[df['Performance (%)'] < 3.0].copy()
            
            st.subheader("🏢 Signale nach Sektor (< 3% Performance)")
            if not df_chart_filtered.empty and 'sector' in df_chart_filtered.columns:
                sector_counts = df_chart_filtered['sector'].value_counts().reset_index()
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
                st.write("Keine Signale mit weniger als 3% Performance gefunden.")
            
            # 5. EMA Performance Check
            st.divider()
            st.subheader("📈 Performance-Check: Filter-Effizienz")
            
            df_ueber_all = df[df['EMA20_Dist_%'] >= 0]
            df_unter_all = df[df['EMA20_Dist_%'] < 0]
            
            col1, col2 = st.columns(2)
            avg_ueber = df_ueber_all['Performance (%)'].mean() if not df_ueber_all.empty else 0
            avg_unter = df_unter_all['Performance (%)'].mean() if not df_unter_all.empty else 0
            
            with col1:
                st.metric(label="Ø Performance (Über EMA20)", value=f"{avg_ueber:.2f}%", delta=f"{avg_ueber - avg_unter:.2f}% vs. Unter EMA")
            with col2:
                st.metric(label="Ø Performance (Unter EMA20)", value=f"{avg_unter:.2f}%")
            st.caption(f"Anzahl Signale über EMA: {len(df_ueber_all)} | Anzahl unter EMA: {len(df_unter_all)}")

            # 6. Signal-Listen mit Favoriten-Funktion & Tabellen-Editor
            st.divider()
            st.subheader("📋 Signal-Listen & Favoriten")
            
            tab_favs, tab_ueber, tab_unter = st.tabs(["⭐ Favoriten", "🚀 Über EMA20 (Trend)", "⚠️ Unter EMA20 (Dip/Reversal)"])
            
            cols_to_show = ['Action', 'ticker', 'company_name', 'sector', 'signal_type', 'Performance (%)', 'EMA20_Dist_%', 'entry_price', 'candle_time', 'TV_Link']
            
            col_config = {
                "Action": st.column_config.CheckboxColumn("Entfernen" if 'is_fav_view' in locals() else "Zu Favoriten", default=False),
                "TV_Link": st.column_config.LinkColumn("TradingView", display_text="Analyse"),
                "Performance (%)": st.column_config.NumberColumn("Performance (%)", format="%.2f%%"),
                "EMA20_Dist_%": st.column_config.NumberColumn("EMA20 Dist. %", format="%.2f%%"),
                "entry_price": st.column_config.NumberColumn("Einstieg", format="%.2f €"),
                "candle_time": st.column_config.TextColumn("Kerzen-Zeit")
            }

            def show_editable_table(df_subset, is_fav_view=False):
                if df_subset.empty:
                    st.info("Keine Einträge.")
                    return

                df_editor = df_subset.copy()
                df_editor['Action'] = False 
                
                existing_cols = [c for c in cols_to_show if c in df_editor.columns]

                # Dynamische Spaltenkonfiguration je nach Tab
                local_config = col_config.copy()
                local_config["Action"] = st.column_config.CheckboxColumn("Entfernen" if is_fav_view else "Zu Favoriten", default=False)

                edited_df = st.data_editor(
                    df_editor[existing_cols],
                    column_config=local_config,
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

            with tab_favs:
                show_editable_table(df[df['status'] == 'favorite'], is_fav_view=True)
            with tab_ueber:
                show_editable_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] >= 0)], is_fav_view=False)
            with tab_unter:
                show_editable_table(df[(df['status'] == 'signal') & (df['EMA20_Dist_%'] < 0)], is_fav_view=False)

        else:
            st.info("Tabelle 'signals' ist leer.")
            
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")