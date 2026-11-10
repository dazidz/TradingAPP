from datetime import datetime, date
import os
import pandas as pd
import streamlit as st
import yfinance as yf

# Seiteneinstellungen
st.set_page_config(layout="wide", page_title="VisionDZ - Terminal", page_icon="⚡")

# --- ULTRA-KOMPAKTES TERMINAL STYLING ---
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
        background-color: #0d1117;
    }
    .section-header {
        font-size: 0.8rem;
        font-weight: 600;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-top: 1rem;
        margin-bottom: 0.4rem;
        border-bottom: 1px solid #21262d;
        padding-bottom: 3px;
    }
    .box-title {
        font-size: 0.75rem;
        font-weight: 600;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 8px;
        border-bottom: 1px solid #30363d;
        padding-bottom: 4px;
    }
    .t-card {
        background-color: #0d1117;
        border: 1px solid #21262d;
        border-radius: 4px;
        padding: 6px 8px;
        margin-bottom: 6px;
    }
    /* BESCHRIFTUNG GROSS & FETT */
    .t-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #f0f6fc;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    /* KURS دېZENTER / KLEINER */
    .t-value {
        font-size: 0.75rem;
        font-weight: 400;
        color: #c9d1d9;
    }
    .t-pos {
        color: #3fb950;
        font-weight: 600;
        font-size: 0.68rem;
    }
    .t-neg {
        color: #da3633;
        font-weight: 600;
        font-size: 0.68rem;
    }
    </style>
""", unsafe_allow_html=True)

def _get_supabase_client():
    url, key = None, None
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        pass
    if not url:
        url = os.environ.get("SUPABASE_URL")
    if not key:
        key = os.environ.get("SUPABASE_KEY")
    from supabase import create_client
    return create_client(url, key)

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
            try:
                app_password = st.secrets["APP_PASSWORD"]
            except Exception:
                app_password = os.environ.get("APP_PASSWORD", "")
                
            if input_pw == app_password:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("Passwort falsch.")
    return False

# --- Sichere Render-Funktion für ein einzelnes Kästchen ---
def render_card(title, value, pct=None, unit=""):
    pct_html = ""
    if pct is not None:
        cls = "t-pos" if pct >= 0 else "t-neg"
        sign = "+" if pct > 0 else ""
        pct_html = f'<span class="{cls}">{sign}{pct:.2f}%</span>'
    
    html = f"""
        <div class="t-card">
            <div class="t-title">{title}</div>
            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                <span class="t-value">{value} {unit}</span>
                {pct_html}
            </div>
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- Datenabrufe ---
@st.cache_data(ttl=60)
def get_macro_commodities():
    # Um Silber und Kupfer erweitert
    symbols = {
        "Gold": "GC=F", 
        "Silber": "SI=F", 
        "Kupfer": "HG=F", 
        "Rohöl (WTI)": "CL=F", 
        "US 10Y Zins": "^TNX", 
        "Bitcoin": "BTC-USD"
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

@st.cache_data(ttl=60)
def get_sector_performance():
    try:
        sup_client = _get_supabase_client()
        response = sup_client.table("watchlist").select("*").execute()
        df = pd.DataFrame(response.data)
        if df.empty:
            return pd.Series(dtype=float)
        
        ticker_col = next((c for c in ['ticker', 'symbol', 'aktie'] if c in df.columns), None)
        sector_col = next((c for c in ['sector', 'sektor', 'strategy_kategorie'] if c in df.columns), None)
        
        if not ticker_col or not sector_col:
            return pd.Series(dtype=float)
        
        tickers = df[ticker_col].dropna().astype(str).str.strip().unique().tolist()
        if not tickers:
            return pd.Series(dtype=float)
            
        data = yf.download(tickers, period="2d", interval="1d", progress=False, auto_adjust=True)
        if data.empty:
            return pd.Series(dtype=float)
            
        if isinstance(data.columns, pd.MultiIndex):
            if 'Close' in data.columns.levels[0]:
                df_close = data['Close']
            else:
                df_close = data.iloc[:, :len(tickers)]
        else:
            df_close = data[['Close']] if 'Close' in data.columns else data
            
        if len(df_close) >= 2:
            pct_changes = (df_close.iloc[-1] / df_close.iloc[-2] - 1) * 100
            perf_df = pd.DataFrame({'ticker_clean': pct_changes.index, 'daily_return_pct': pct_changes.values})
            
            df['ticker_clean'] = df[ticker_col].astype(str).str.strip()
            merged = pd.merge(df, perf_df, on='ticker_clean', how='inner')
            
            if not merged.empty and 'daily_return_pct' in merged.columns:
                sector_perf = merged.groupby(sector_col)['daily_return_pct'].mean().sort_values(ascending=False)
                return sector_perf
        return pd.Series(dtype=float)
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=60)
def get_watchlist_performance():
    try:
        sup_client = _get_supabase_client()
        response = sup_client.table("watchlist").select("*").execute()
        df = pd.DataFrame(response.data)
        if df.empty: return pd.DataFrame()
        
        ticker_col = next((c for c in ['ticker', 'symbol', 'aktie'] if c in df.columns), None)
        name_col = next((c for c in ['company_name', 'name', 'unternehmen'] if c in df.columns), ticker_col)
        sector_col = next((c for c in ['sector', 'sektor', 'strategy_kategorie'] if c in df.columns), None)
        gettex_col = next((c for c in ['gettex_ticker', 'gettex'] if c in df.columns), None)
        
        if not ticker_col: return pd.DataFrame()
        
        performances = []
        for _, row in df.iterrows():
            t_str = str(row[ticker_col]).strip()
            try:
                ticker_obj = yf.Ticker(t_str)
                info = ticker_obj.info
                curr = info.get('currentPrice') or info.get('regularMarketPrice')
                prev = info.get('previousClose')
                
                if curr and prev:
                    gt_tick = row[gettex_col] if gettex_col and pd.notna(row[gettex_col]) else t_str
                    performances.append({
                        "Firma": row[name_col] if name_col else t_str,
                        "Sektor": row[sector_col] if sector_col and pd.notna(row[sector_col]) else "N/A",
                        "Chart": f"https://www.tradingview.com/chart/?symbol={gt_tick}",
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
    # Header
    col_head1, col_head2 = st.columns([3, 1])
    with col_head1:
        st.markdown("<h3 style='color: #f0f6fc; margin: 0; font-family: monospace;'>⚡ V I S I O N D Z // TERMINAL</h3>", unsafe_allow_html=True)
    with col_head2:
        st.markdown(f"<div style='text-align: right; color: #8b949e; font-size: 0.7rem; font-family: monospace;'>SYS: <span style='color: #3fb950;'>ONLINE</span> | {date.today().strftime('%d.%m.%Y')}</div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 1px; background-color: #30363d; margin: 0.5rem 0 0.8rem 0;'></div>", unsafe_allow_html=True)

    # --- EARNINGS WARNER (0 <= days_until <= 2) ---
    try:
        sup_client = _get_supabase_client()
        swing_res = sup_client.table("swing_depot").select("*").execute()
        swing_positions = swing_res.data if swing_res.data else []
        
        if swing_positions:
            upcoming_earnings = []
            for pos in swing_positions:
                t = pos.get("ticker") or pos.get("symbol")
                comp_name = pos.get("unternehmen") or pos.get("name") or t
                if not t: continue
                try:
                    ticker_obj = yf.Ticker(t)
                    cal = ticker_obj.calendar
                    earnings_date = None
                    if isinstance(cal, dict) and "Earnings Date" in cal:
                        dates = cal["Earnings Date"]
                        if isinstance(dates, list) and len(dates) > 0:
                            earnings_date = pd.to_datetime(dates[0]).date()
                    
                    if not earnings_date:
                        ed_df = ticker_obj.get_earnings_dates(limit=2)
                        if ed_df is not None and not ed_df.empty:
                            future_dates = ed_df.index[ed_df.index >= pd.Timestamp.today()]
                            if len(future_dates) > 0:
                                earnings_date = future_dates[0].date()

                    if earnings_date:
                        days_until = (earnings_date - date.today()).days
                        if 0 <= days_until <= 2:
                            upcoming_earnings.append({
                                "Ticker": t,
                                "Unternehmen": comp_name,
                                "Earnings Datum": earnings_date,
                                "Tage bis Earnings": days_until
                            })
                except Exception:
                    continue

            if upcoming_earnings:
                st.markdown('<div class="section-header">🚨 Earnings Warner (Swing Depot)</div>', unsafe_allow_html=True)
                for row in sorted(upcoming_earnings, key=lambda x: x["Tage bis Earnings"]):
                    if row["Tage bis Earnings"] == 0:
                        timing_text = "HEUTE!"
                        badge_color = "#da3633"
                    elif row["Tage bis Earnings"] == 1:
                        timing_text = "Morgen"
                        badge_color = "#d29922"
                    else:
                        timing_text = "in 2 Tagen"
                        badge_color = "#d29922"

                    st.markdown(
                        f"""<div style="border-left: 3px solid {badge_color}; background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; padding: 8px 12px;">
                            <div>
                                <span style="font-weight: 600; color: #f0f6fc; font-size: 0.85rem;">{row['Unternehmen']} ({row['Ticker']})</span><br>
                                <span style="color: #8b949e; font-size: 0.7rem;">Quartalszahlen am <b>{row['Earnings Datum'].strftime('%d.%m.%Y')}</b></span>
                            </div>
                            <div style="background-color: {badge_color}; color: #ffffff; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 0.65rem;">
                                {timing_text}
                            </div>
                        </div>""",
                        unsafe_allow_html=True
                    )
    except Exception:
        pass

    # --- ZWEI HAUPTBOXEN NEBENEINANDER (Mit nativen st.container Rahmen) ---
    col_box1, col_box2 = st.columns(2)
    
    # --- LINKE BOX: MAKRO, ROHSTOFFE & CRYPTO ---
    with col_box1:
        with st.container(border=True):
            st.markdown('<div class="box-title">🌍 Makro, Rohstoffe & Crypto</div>', unsafe_allow_html=True)
            macro_data = get_macro_commodities()
            items = list(macro_data.items()) # Gold, Silber, Kupfer, Rohöl, Zins, Bitcoin
            
            # Dynamisch paarweise in Reihen aufteilen
            for i in range(0, len(items), 2):
                r_c1, r_c2 = st.columns(2)
                with r_c1:
                    render_card(items[i][0], f"{items[i][1]['price']:,.2f}", items[i][1]['pct'], items[i][1]['unit'])
                if i + 1 < len(items):
                    with r_c2:
                        render_card(items[i+1][0], f"{items[i+1][1]['price']:,.2f}", items[i+1][1]['pct'], items[i+1][1]['unit'])
        
    # --- RECHTE BOX: GLOBALE MÄRKTE & INDIZES ---
    with col_box2:
        with st.container(border=True):
            st.markdown('<div class="box-title">📊 Globale Märkte & Indizes</div>', unsafe_allow_html=True)
            index_data = get_index_performance()
            idx_items = list(index_data.items())
            
            for i in range(0, len(idx_items), 2):
                row_c1, row_c2 = st.columns(2)
                with row_c1:
                    name, val = idx_items[i]
                    render_card(name, f"{val['price']:,.2f}", val['pct'])
                if i + 1 < len(idx_items):
                    with row_c2:
                        name, val = idx_items[i + 1]
                        render_card(name, f"{val['price']:,.2f}", val['pct'])

    # --- SEKTOR-PERFORMANCE ---
    st.markdown('<div class="section-header">🏛️ Sektor-Übersicht (Tagesperformance)</div>', unsafe_allow_html=True)
    sector_perf = get_sector_performance()
    
    if not sector_perf.empty:
        sectors = list(sector_perf.items())
        cols_sec = st.columns(min(len(sectors), 6))
        for idx, (sec_name, sec_val) in enumerate(sectors):
            col_idx = idx % len(cols_sec)
            with cols_sec[col_idx]:
                render_card(sec_name, f"{sec_val:.2f}%", sec_val)
    else:
        st.info("Keine Sektor-Daten verfügbar.")

    # --- TOP GEWINNER & VERLIERER ---
    st.markdown('<div class="section-header">⚡ Top Performance Watchlist</div>', unsafe_allow_html=True)
    df_perf = get_watchlist_performance()

    if not df_perf.empty and "Tageschange (%)" in df_perf.columns:
        df_sorted = df_perf.sort_values(by="Tageschange (%)", ascending=False)
        col_win, col_loss = st.columns(2)
        
        conf = {
            "Chart": st.column_config.LinkColumn("TradingView", display_text="📈 Öffnen"),
            "Tageschange (%)": st.column_config.NumberColumn(format="%.2f%%")
        }
        
        with col_win:
            st.markdown("<span style='color: #3fb950; font-weight: 600; font-size: 0.75rem;'>🟢 TOP GEWINNER</span>", unsafe_allow_html=True)
            st.dataframe(df_sorted.head(10), column_config=conf, hide_index=True, use_container_width=True)
        with col_loss:
            st.markdown("<span style='color: #da3633; font-weight: 600; font-size: 0.75rem;'>🔴 TOP VERLIERER</span>", unsafe_allow_html=True)
            st.dataframe(df_sorted.tail(10).sort_values(by="Tageschange (%)"), column_config=conf, hide_index=True, use_container_width=True)
    else:
        st.info("Keine Watchlist-Daten verfügbar.")