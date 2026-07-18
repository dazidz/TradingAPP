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
            # 1. Dubletten bereinigen (behält immer das aktuellste Signal pro Ticker/Typ)
            df = df.sort_values('created_at', ascending=True)
            df = df.drop_duplicates(subset=['ticker', 'signal_type'], keep='last')

            # 2. Spalten-Mapping & Metadaten
            if 'signal' in df.columns: df = df.rename(columns={'signal': 'signal_type'})
            if 'meta_data' in df.columns:
                df['meta_data'] = df['meta_data'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else {})
                meta_df = pd.json_normalize(df['meta_data'])
                df = pd.concat([df.drop('meta_data', axis=1), meta_df], axis=1)

            if 'gettex_ticker' in df.columns:
                df['TV_Link'] = df['gettex_ticker'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else "")
            
            # 3. Performance & Kurse
            df['entry_price'] = pd.to_numeric(df['entry_price'], errors='coerce')
            unique_tickers = df['ticker'].unique().tolist()
            
            with st.spinner("Lade Live-Kurse..."):
                price_map = get_all_prices(unique_tickers)
            
            df['current_price'] = df['ticker'].map(price_map)
            df['Performance (%)'] = ((df['current_price'] - df['entry_price']) / df['entry_price']) * 100
            
            # 4. Sektoren-Visualisierung (Altair Horizontal Bar Chart)
            st.subheader("🏢 Signale nach Sektor")
            if 'sector' in df.columns:
                sector_counts = df['sector'].value_counts().reset_index()
                sector_counts.columns = ['Sektor', 'Anzahl']
                
                # Wir legen eine Spalten-Struktur an (2/3 Breite für das Chart, 1/3 bleibt leer)
                col_chart, col_empty = st.columns([2, 1])
                
                with col_chart:
                    chart_height = len(sector_counts) * 35 
                    
                    chart = alt.Chart(sector_counts).mark_bar(
                        color='#3b82f6',
                        size=20
                    ).encode(
                        # Wir setzen das Maximum der X-Achse auf den höchsten Wert + Puffer,
                        # damit der Balken optisch bei 2/3 endet
                        x=alt.X('Anzahl:Q', title='Anzahl Signale', scale=alt.Scale(domain=[0, sector_counts['Anzahl'].max() * 1.5])),
                        y=alt.Y('Sektor:N', sort='-x', title=None),
                        tooltip=['Sektor', 'Anzahl']
                    ).properties(
                        height=chart_height
                    )
                    
                    st.altair_chart(chart, use_container_width=True)
            else:
                st.write("Keine Sektoren-Daten.")
            
            # 5. Signal-Liste
            st.subheader("📋 Signal-Liste")
            cols_to_show = ['company_name', 'sector', 'signal_type', 'Performance (%)', 'entry_price', 'candle_time', 'TV_Link']
            existing_cols = [c for c in cols_to_show if c in df.columns]
            
            st.dataframe(
                df[existing_cols], 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "TV_Link": st.column_config.LinkColumn("TradingView", display_text="Analyse"),
                    "Performance (%)": st.column_config.NumberColumn("Performance (%)", format="%.2f%%"),
                    "entry_price": st.column_config.NumberColumn("Einstieg", format="%.2f €")
                }
            )
        else:
            st.info("Tabelle 'signals' ist leer.")
            
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")