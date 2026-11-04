from datetime import datetime, date
import os
import pandas as pd
import streamlit as st
import yfinance as yf

# Seiteneinstellungen
st.set_page_config(layout="wide", page_title="VisionDZ - Terminal", page_icon="⚡")

# --- ULTRA-KOMPAKTES TERMINAL CSS & GRID ---
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
        background-color: #0d1117;
    }
    /* Responsives Terminal-Grid für ultrakompakte Karten */
    .terminal-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
        gap: 6px;
        margin-bottom: 0.8rem;
    }
    .t-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 4px;
        padding: 8px 10px;
        transition: border-color 0.2s ease;
    }
    .t-card:hover {
        border-color: #58a6ff;
    }
    .t-title {
        font-size: 0.68rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 2px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .t-value {
        font-size: 1.05rem;
        font-weight: 600;
        color: #f0f6fc;
    }
    .t-pos {
        color: #3fb950;
        font-weight: 600;
        font-size: 0.75rem;
    }
    .t-neg {
        color: #da3633;
        font-weight: 600;
        font-size: 0.75rem;
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

# --- HTML Renderer für Grid-Karten ---
def render_html_card(title, value, pct=None, unit=""):
    pct_html = ""
    if pct is not None:
        cls = "t-pos" if pct >= 0 else "t-neg"
        sign = "+" if pct > 0 else ""
        pct_html = f'<span class="{cls}">{sign}{pct:.2f}%</span>'
    
    return f"""
        <div class="t-card">
            <div class="t-title">{title}</div>
            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                <span class="t-value">{value} {unit}</span>
                {pct_html}
            </div>
        </div>
    """

# --- Datenabrufe ---
@st.cache_data(ttl=60)
def get_macro_commodities():
    symbols = {"Gold": "GC=F", "Rohöl (WTI)": "CL=F", "US 10Y Zins": "^TNX"}
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
        response = sup_client.table("watchlist").select("ticker, sector").execute()
        df = pd.DataFrame(response.data)
        if df.empty or 'sector' not in df.columns or 'ticker' not in df.columns:
            return pd.Series(dtype=float)
        
        tickers = df['ticker'].dropna().unique().tolist()
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
            pct_changes = df_close.iloc[-1] / df_close.iloc[-2] - 1
            pct_changes = pct_changes * 100
            
            perf_df = pd.DataFrame({'ticker': pct_changes.index, 'daily_return_pct': pct_changes.values})
            merged = pd.merge(df, perf_df, on='ticker', how='inner')
            
            if not merged.empty and 'daily_return_pct' in merged.columns:
                sector_perf = merged.groupby('sector')['daily_return_pct'].mean().sort_values(ascending=False)
                return sector_perf
        return pd.Series(dtype=float)
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=60)
def get_watchlist_performance():
    try:
        sup_client = _get_supabase_client()
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
    # Header
    col_head1, col_head2 = st.columns([3, 1])
    with col_head1:
        st.markdown("<h3 style='color: #f0f6fc; margin: 0; font-family: monospace;'>⚡ V I S I O N D Z // TERMINAL</h3>", unsafe_allow_html=True)
    with col_head2:
        st.markdown(f"<div style='text-align: right; color: #8b949e; font-size: 0.7rem; font-family: monospace;'>SYS: <span style='color: #3fb950;'>ONLINE</span> | {date.today().strftime('%d.%m.%Y')}</div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 1px; background-color: #30363d; margin: 0.5rem 0 0.8rem 0;'></div>", unsafe_allow_html=True)

    # --- EARNINGS WARNER (Exakt 2 Tage vorher bis zum Tag selbst: 0 <= days_until <= 2) ---
    try:
        sup_client = _get_supabase_client()
        swing_res = sup_client.table("swing_depot").select("ticker, unternehmen").execute()
        swing_positions = swing_res.data if swing_res.data else []
        
        if swing_positions:
            upcoming_earnings = []
            for pos in swing_positions:
                t = pos["ticker"]
                comp_name = pos.get("unternehmen", t)
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
                        f"""<div class="t-card" style="border-left: 3px solid {badge_color}; display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
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

    # --- 1. & 2. GEMEINSAME EBENE: MÄRKTE & ROHSTOFFE (CSS GRID) ---
    st.markdown('<div class="section-header">🌍 Märkte, Indizes & Rohstoffe</div>', unsafe_allow_html=True)
    
    macro_data = get_macro_commodities()
    index_data = get_index_performance()
    
    grid_html = '<div class="terminal-grid">'
    
    # Rohstoffe einfügen
    for m_name, m_val in macro_data.items():
        grid_html += render_html_card(m_name, f"{m_val['price']:,.2f}", m_val['pct'], m_val['unit'])
        
    # Indizes einfügen
    for idx_name, val in index_data.items():
        grid_html += render_html_card(idx_name, f"{val['price']:,.2f}", val['pct'])
        
    grid_html += '</div>'
    st.markdown(grid_html, unsafe_allow_html=True)

    # --- 3. SEKTOR-PERFORMANCE ---
    st.markdown('<div class="section-header">🏛️ Sektor-Übersicht (Tagesperformance)</div>', unsafe_allow_html=True)
    sector_perf = get_sector_performance()
    
    if not sector_perf.empty:
        sec_grid = '<div class="terminal-grid">'
        for sec_name, sec_val in sector_perf.items():
            sec_grid += render_html_card(sec_name, f"{sec_val:.2f}%", sec_val)
        sec_grid += '</div>'
        st.markdown(sec_grid, unsafe_allow_html=True)
    else:
        st.info("Keine Sektor-Daten verfügbar.")

    # --- 4. TOP GEWINNER & VERLIERER ---
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