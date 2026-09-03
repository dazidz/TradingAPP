import streamlit as st
import traceback

# Seiteneinstellungen
st.set_page_config(layout="wide", page_title="VisionDZ - Dashboard", page_icon="📈")

try:
    from supabase import create_client
    import pandas as pd
    import yfinance as yf

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

    # Verbindung zu Supabase prüfen
    if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
        st.error("❌ Fehler: Supabase-Zugangsdaten (`SUPABASE_URL` oder `SUPABASE_KEY`) fehlen in den Streamlit Secrets (`secrets.toml`).")
        st.stop()

    URL = st.secrets["SUPABASE_URL"]
    KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(URL, KEY)

    def check_password():
        if "APP_PASSWORD" not in st.secrets:
            return True
            
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

    # Robuste Index-Daten
    @st.cache_data(ttl=60)
    def get_index_performance():
        indices = {
            "S&P 500": "^GSPC", "Nasdaq 100": "^NDX", "DAX": "^GDAXI", "Euro Stoxx 50": "^STOXX50E",
            "Dow Jones": "^DJI", "Russell 2000": "^RUT", "Nikkei 225": "^N225", "KOSPI": "^KS11"
        }
        results = {}
        for name, symbol in indices.items():
            try:
                df = yf.download(symbol, period="2d", progress=False)
                if not df.empty and 'Close' in df.columns:
                    close_series = df['Close'].dropna()
                    if isinstance(close_series, pd.DataFrame):
                        close_series = close_series.iloc[:, 0]
                    if len(close_series) >= 2:
                        current = float(close_series.iloc[-1])
                        prev = float(close_series.iloc[-2])
                        results[name] = {"price": current, "pct": ((current - prev) / prev) * 100}
                        continue
            except Exception:
                pass
            results[name] = {"price": 0.0, "pct": 0.0}
        return results

    # Makro- & Rohstoff-Daten
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

    # Sektor-Performance
    @st.cache_data(ttl=60)
    def get_sector_performance():
        try:
            response = supabase.table("watchlist").select("ticker, sector").execute()
            df = pd.DataFrame(response.data)
            if df.empty or 'sector' not in df.columns or 'ticker' not in df.columns:
                return pd.Series()
            
            tickers = df['ticker'].dropna().unique().tolist()
            if not tickers:
                return pd.Series()
                
            pct_dict = {}
            for t in tickers:
                try:
                    tdf = yf.download(t, period="2d", progress=False)
                    if not tdf.empty and 'Close' in tdf.columns:
                        c = tdf['Close'].dropna()
                        if isinstance(c, pd.DataFrame):
                            c = c.iloc[:, 0]
                        if len(c) >= 2:
                            pct_dict[t] = ((float(c.iloc[-1]) - float(c.iloc[-2])) / float(c.iloc[-2])) * 100
                except Exception:
                    continue
                    
            if not pct_dict:
                return pd.Series()
                
            perf_df = pd.DataFrame(list(pct_dict.items()), columns=['ticker', 'daily_return_pct'])
            merged = pd.merge(df, perf_df, on='ticker', how='inner')
            
            if not merged.empty:
                return merged.groupby('sector')['daily_return_pct'].mean().sort_values(ascending=False)
            return pd.Series()
        except Exception:
            return pd.Series()

    # Watchlist-Performance
    @st.cache_data(ttl=60)
    def get_watchlist_performance():
        try:
            response = supabase.table("watchlist").select("ticker, company_name, gettex_ticker, sector").execute()
            df = pd.DataFrame(response.data)
            if df.empty: return pd.DataFrame()
            
            performances = []
            for _, row in df.iterrows():
                try:
                    tdf = yf.download(row['ticker'], period="2d", progress=False)
                    if not tdf.empty and 'Close' in tdf.columns:
                        c = tdf['Close'].dropna()
                        if isinstance(c, pd.DataFrame):
                            c = c.iloc[:, 0]
                        if len(c) >= 2:
                            curr = float(c.iloc[-1])
                            prev = float(c.iloc[-2])
                            performances.append({
                                "Firma": row['company_name'],
                                "Sektor": row.get('sector', 'N/A'),
                                "Chart": f"https://www.tradingview.com/chart/?symbol={row['gettex_ticker']}" if row.get('gettex_ticker') else f"https://www.tradingview.com/chart/?symbol={row['ticker']}",
                                "Aktuell": round(curr, 2),
                                "Tageschange (%)": round(((curr - prev) / prev) * 100, 2)
                            })
                except Exception:
                    continue
            return pd.DataFrame(performances)
        except Exception:
            return pd.DataFrame()

    # --- HAUPTPROGRAMM ---
    if check_password():
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
        
        # 3. Sektor Performance
        st.subheader("🏛️ Sektor-Übersicht (Tagesperformance)")
        sector_perf = get_sector_performance()
        
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

except Exception as e:
    st.error("🚨 Ein Fehler ist im Hauptskript aufgetreten:")
    st.exception(e)