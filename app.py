import streamlit as st
from supabase import create_client
import pandas as pd
import yfinance as yf

# Seiteneinstellungen
st.set_page_config(layout="wide", page_title="VisionDZ - Dashboard", page_icon="📈")

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

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

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

# --- Makro- & Rohstoff-Daten ---
@st.cache_data(ttl=60)
def get_macro_commodities():
    symbols = {
        "Gold": "GC=F",
        "Rohöl (WTI)": "CL=F",
        "US 10Y Zins": "^TNX"
    }
    results = {}
    for name, symbol in symbols.items():
        try:
            df = yf.download(symbol, period="2d", progress=False)
            if not df.empty and 'Close' in df.columns:
                close_series = df['Close'].dropna()
                if isinstance(close_series, pd.DataFrame):
                    close_series = close_series.iloc[:, 0]
                if len(close_series) >= 2:
                    current = float(close_series.iloc[-1])
                    prev = float(close_series.iloc[-2])
                    unit = "%" if symbol == "^TNX" else "$"
                    results[name] = {"price": current, "pct": ((current - prev) / prev) * 100, "unit": unit}
                    continue
        except Exception:
            pass
        results[name] = {"price": 0.0, "pct": 0.0, "unit": ""}
    return results

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

# Sektor-Performance berechnen
@st.cache_data(ttl=60)
def get_sector_performance(sup_client):
    try:
        response = sup_client.table("watchlist").select("ticker, sector").execute()
        df = pd.DataFrame(response.data)
        if df.empty or 'sector' not in df.columns or 'ticker' not in df.columns:
            return pd.Series()
        
        tickers = df['ticker'].dropna().unique().tolist()
        if not tickers:
            return pd.Series()
            
        data = yf.download(tickers, period="2d", interval="1d", progress=False, auto_adjust=True)
        if data.empty:
            return pd.Series()
            
        if isinstance(data.columns, pd.MultiIndex):
            if 'Close' in data.columns.levels[0]:
                df_close = data['Close']
            else:
                df_close = data.iloc[:, :len(tickers)]
        else:
            df_close = data[['Close']] if 'Close' in data.columns else data
            
        if len(df_close) >= 2:
            pct_changes = df_close.iloc[-1] / df_close.iloc[-2] - 1
            pct_changes = pct_changes * 100
            
            perf_df = pd.DataFrame({'ticker': pct_changes.index, 'daily_return_pct': pct_changes.values})
            merged = pd.merge(df, perf_df, on='ticker', how='inner')
            
            if not merged.empty and 'daily_return_pct' in merged.columns:
                sector_perf = merged.groupby('sector')['daily_return_pct'].mean().sort_values(ascending=False)
                return sector_perf
        return pd.Series()
    except Exception:
        return pd.Series()

# Präzise Watchlist-Performance
@st.cache_data(ttl=60)
def get_watchlist_performance(sup_client):
    try:
        response = sup_client.table("watchlist").select("ticker, company_name, gettex_ticker, sector").execute()
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
                        "Sektor": row.get('sector', 'N/A'),
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
    # Verbindung zu Supabase erst nach erfolgreichem Login herstellen
    URL = st.secrets["SUPABASE_URL"]
    KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(URL, KEY)

    st.title("📈 VisionDZ - Dashboard")
    
    # 1. Makro & Rohstoffe
    st.subheader("🌍 Makro & Rohstoffe")
    macro_data = get_macro_commodities()
    if macro_data:
        cols_macro = st.columns(len(macro_data))
        for idx, (m_name, m_val) in enumerate(macro_data.items()):
            val_str = f"{m_val['price']:,.2f} {m_val['unit']}"
            cols_macro[idx].metric(m_name, val_str, f"{m_val['pct']:.2f}%")
        
    st.divider()
    
    # 2. Globale Indizes
    st.subheader("📊 Globale Märkte")
    index_data = get_index_performance()
    keys = list(index_data.keys())
    
    for r in range(2):
        cols = st.columns(4)
        for i in range(4):
            if r*4 + i < len(keys):
                idx_name = keys[r*4 + i]
                val = index_data[idx_name]
                cols[i].metric(idx_name, f"{val['price']:,.2f}", f"{val['pct']:.2f}%")
    
    st.divider()
    
    # 3. Sektor-Performance
    st.subheader("🏛️ Sektor-Übersicht (Tagesperformance)")
    sector_perf = get_sector_performance(supabase)
    
    if not sector_perf.empty:
        sectors = list(sector_perf.items())
        num_sectors = len(sectors)
        cols_per_row = min(num_sectors, 4)
        for i in range(0, num_sectors, cols_per_row):
            row_sectors = sectors[i:i + cols_per_row]
            cols = st.columns(len(row_sectors))
            for col_idx, (sec_name, sec_val) in enumerate(row_sectors):
                cols[col_idx].metric(
                    label=sec_name, 
                    value=f"{sec_val:.2f}%", 
                    delta=f"{sec_val:.2f}%"
                )
    else:
        st.info("Keine Sektor-Daten verfügbar.")
        
    st.divider()
    
    # 4. Top Gewinner & Verlierer
    df_perf = get_watchlist_performance(supabase)

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