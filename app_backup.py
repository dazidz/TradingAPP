import streamlit as st
from supabase import create_client
import pandas as pd
import yfinance as yf

# Seiteneinstellungen
st.set_page_config(layout="wide", page_title="Trading Dashboard", page_icon="📈")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    div[data-testid="metric-container"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        padding: 14px 18px;
        border-radius: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

def check_password():
    # Initialisierung im Session State, falls noch nicht vorhanden
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    # Wenn bereits erfolgreich eingeloggt, direkt True zurückgeben
    if st.session_state.password_correct:
        return True

    # Login-Maske anzeigen
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🔐 Login")
        input_pw = st.text_input("Passwort:", type="password", key="login_password_input")
        if st.button("Anmelden", use_container_width=True):
            if input_pw == st.secrets["APP_PASSWORD"]:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("Passwort falsch.")
    return False

# Robuste Index-Daten (MultiIndex-sicher)
@st.cache_data(ttl=60)
def get_index_performance():
    indices = {
        "S&P 500": "^GSPC", "Nasdaq 100": "^NDX", "DAX": "^GDAXI", "Euro Stoxx 50": "^STOXX50E",
        "Dow Jones": "^DJI", "Russell 2000": "^RUT", "Nikkei 225": "^N225", "KOSPI": "^KS11"
    }
    results = {}
    try:
        data = yf.download(list(indices.values()), period="2d", group_by='ticker', progress=False, multi_level_index=False)
    except Exception:
        data = yf.download(list(indices.values()), period="2d", group_by='ticker', progress=False)

    for name, symbol in indices.items():
        try:
            if isinstance(data.columns, pd.MultiIndex):
                df_idx = data[symbol]
            else:
                df_idx = data
            
            close_series = df_idx['Close'][symbol] if symbol in df_idx.columns else df_idx['Close']
            close_series = close_series.dropna()
            
            if len(close_series) >= 2:
                current = float(close_series.iloc[-1])
                prev = float(close_series.iloc[-2])
                results[name] = {"price": current, "pct": ((current - prev) / prev) * 100}
            else:
                results[name] = {"price": 0.0, "pct": 0.0}
        except Exception:
            results[name] = {"price": 0.0, "pct": 0.0}
    return results

# Präzise Watchlist-Performance (Live gegen Vortagesschluss)
@st.cache_data(ttl=60)
def get_watchlist_performance():
    try:
        response = supabase.table("watchlist").select("ticker, company_name, gettex_ticker").execute()
        df = pd.DataFrame(response.data)
        if df.empty: return pd.DataFrame()
        
        performances = []
        for _, row in df.iterrows():
            try:
                ticker = yf.Ticker(row['ticker'])
                info = ticker.info
                curr = info.get('currentPrice') or info.get('regularMarketPrice')
                prev = info.get('previousClose')
                
                if curr and prev:
                    performances.append({
                        "Firma": row['company_name'],
                        "Chart": f"https://www.tradingview.com/chart/?symbol={row['gettex_ticker']}" if row['gettex_ticker'] else f"https://www.tradingview.com/chart/?symbol={row['ticker']}",
                        "Aktuell": round(float(curr), 2),
                        "Tageschange (%)": round(((curr - prev) / prev) * 100, 2)
                    })
            except Exception:
                continue
        return pd.DataFrame(performances)
    except Exception:
        return pd.DataFrame()

# --- HAUPTPROGRAMM ---
if check_password():
    st.title("📈 Trading Dashboard")
    
    index_data = get_index_performance()
    keys = list(index_data.keys())
    
    # 2 Reihen à 4 Metriken
    for r in range(2):
        cols = st.columns(4)
        for i in range(4):
            idx_name = keys[r*4 + i]
            val = index_data[idx_name]
            cols[i].metric(idx_name, f"{val['price']:,.2f}", f"{val['pct']:.2f}%")
    
    st.divider()
    df_perf = get_watchlist_performance()

    if not df_perf.empty and "Tageschange (%)" in df_perf.columns:
        df_sorted = df_perf.sort_values(by="Tageschange (%)", ascending=False)
        col_win, col_loss = st.columns(2)
        
        conf = {
            "Chart": st.column_config.LinkColumn("TradingView", display_text="📈 Öffnen"),
            "Tageschange (%)": st.column_config.NumberColumn(format="%.2f%%")
        }
        
        with col_win:
            st.markdown("#### 🟢 Top Gewinner")
            st.dataframe(df_sorted.head(10), column_config=conf, hide_index=True, use_container_width=True)
        with col_loss:
            st.markdown("#### 🔴 Top Verlierer")
            st.dataframe(df_sorted.tail(10).sort_values(by="Tageschange (%)"), column_config=conf, hide_index=True, use_container_width=True)
    else:
        st.info("Keine Watchlist-Daten verfügbar.")