import streamlit as st
from supabase import create_client
import pandas as pd
import yfinance as yf

# Seiteneinstellungen
st.set_page_config(layout="wide", page_title="Trading Dashboard")

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

def check_password():
    if "password_correct" not in st.session_state: 
        st.session_state.password_correct = False
    if not st.session_state.password_correct:
        st.title("🔐 Bitte anmelden")
        input_pw = st.text_input("Passwort:", type="password")
        if st.button("Anmelden", use_container_width=True):
            if input_pw == st.secrets["APP_PASSWORD"]:
                st.session_state.password_correct = True
                st.rerun()
            else: 
                st.error("Passwort falsch.")
        return False
    return True

# Robuster Sammel-Download für alle Indizes gleichzeitig
@st.cache_data(ttl=600)
def get_index_performance():
    indices = {
        "S&P 500": "^GSPC",
        "Nasdaq 100": "^NDX",
        "DAX": "^GDAXI",
        "Euro Stoxx 50": "^STOXX50E",
        "Dow Jones": "^DJI",
        "Russell 2000": "^RUT",
        "Nikkei 225": "^N225",
        "KOSPI": "^KS11"
    }
    results = {}
    symbols = list(indices.values())
    names = list(indices.keys())
    
    try:
        # Lädt alle Indizes auf einmal – das ist stabiler bei Yahoo Finance
        data = yf.download(symbols, period="5d", interval="1d", progress=False)['Close']
        
        for name, symbol in indices.items():
            try:
                series = data[symbol].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) >= 2:
                    prev_close = float(series.iloc[-2])
                    current = float(series.iloc[-1])
                    pct = ((current - prev_close) / prev_close) * 100
                    results[name] = {"price": current, "pct": pct}
                else:
                    results[name] = {"price": 0.0, "pct": 0.0}
            except:
                results[name] = {"price": 0.0, "pct": 0.0}
    except:
        for name in indices.keys():
            results[name] = {"price": 0.0, "pct": 0.0}
            
    return results

# Daten für Watchlist-Performance laden
@st.cache_data(ttl=600)
def get_watchlist_performance():
    try:
        response = supabase.table("watchlist").select("ticker, company_name, gettex_ticker").execute()
        df = pd.DataFrame(response.data)
        if df.empty:
            return pd.DataFrame()
        
        tickers = df['ticker'].tolist()
        data = yf.download(tickers, period="5d", interval="1d", progress=False)['Close']
        
        performances = []
        for _, row in df.iterrows():
            t = row['ticker']
            try:
                series = data[t].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) >= 2:
                    prev_close = series.iloc[-2]
                    current_price = series.iloc[-1]
                    pct_change = ((current_price - prev_close) / prev_close) * 100
                    
                    performances.append({
                        "Ticker": t,
                        "Firma": row['company_name'],
                        "Chart": f"https://www.tradingview.com/chart/?symbol={row['gettex_ticker']}" if row['gettex_ticker'] else f"https://www.tradingview.com/chart/?symbol={t}",
                        "Aktuell": round(float(current_price), 2),
                        "Tageschange (%)": round(float(pct_change), 2)
                    })
            except Exception:
                continue
                
        return pd.DataFrame(performances)
    except Exception as e:
        st.error(f"Fehler beim Laden der Watchlist-Daten: {e}")
        return pd.DataFrame()

# --- HAUPTPROGRAMM ---
if check_password():
    st.title("📈 Trading Dashboard")
    st.write("Willkommen zurück! Hier ist dein Marktüberblick und die Performance deiner Watchlist.")
    
    # Indizes in 4er-Spalten anzeigen (über zwei Zeilen)
    index_data = get_index_performance()
    keys = list(index_data.keys())
    
    if len(keys) >= 8:
        # Zeile 1
        cols1 = st.columns(4)
        for i in range(4):
            k = keys[i]
            val = index_data[k]
            price_val = val['price']
            pct_val = val['pct']
            
            cols1[i].metric(
                label=k, 
                value=f"{price_val:,.2f}" if price_val > 0 else "Lade Fehler", 
                delta=f"{pct_val:.2f}%" if price_val > 0 else "--"
            )
            
        # Zeile 2
        cols2 = st.columns(4)
        for i in range(4):
            k = keys[i+4]
            val = index_data[k]
            price_val = val['price']
            pct_val = val['pct']
            
            cols2[i].metric(
                label=k, 
                value=f"{price_val:,.2f}" if price_val > 0 else "Lade Fehler", 
                delta=f"{pct_val:.2f}%" if price_val > 0 else "--"
            )
    
    st.divider()
    st.subheader("🏆 Watchlist: Top 10 Gewinner & Verlierer des Tages")

    df_perf = get_watchlist_performance()

    if not df_perf.empty and "Tageschange (%)" in df_perf.columns:
        df_sorted = df_perf.sort_values(by="Tageschange (%)", ascending=False)
        
        top_gewinner = df_sorted.head(10)
        top_verlierer = df_sorted.tail(10).sort_values(by="Tageschange (%)", ascending=True)

        col_win, col_loss = st.columns(2)

        conf = {
            "Firma": st.column_config.TextColumn("Firma", disabled=True),
            "Chart": st.column_config.LinkColumn("TradingView", display_text="📈 Öffnen"),
            "Aktuell": st.column_config.NumberColumn(format="%.2f €"),
            "Tageschange (%)": st.column_config.NumberColumn(format="%.2f%%")
        }

        with col_win:
            st.markdown("### 🟢 Top 10 Gewinner")
            st.dataframe(
                top_gewinner[['Firma', 'Chart', 'Aktuell', 'Tageschange (%)']],
                column_config=conf,
                hide_index=True,
                use_container_width=True
            )

        with col_loss:
            st.markdown("### 🔴 Top 10 Verlierer")
            st.dataframe(
                top_verlierer[['Firma', 'Chart', 'Aktuell', 'Tageschange (%)']],
                column_config=conf,
                hide_index=True,
                use_container_width=True
            )
    else:
        st.info("Noch keine Ticker in deiner Supabase-Watchlist gefunden oder Daten werden geladen.")