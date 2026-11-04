from datetime import datetime, date
import os
import pandas as pd
import streamlit as st
import yfinance as yf

# Seiteneinstellungen
st.set_page_config(layout="wide", page_title="VisionDZ - Terminal", page_icon="⚡")

# --- ULTRA-KOMPAKTES TERMINAL CSS ---
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
        background-color: #0d1117;
    }
    .t-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 4px;
        padding: 6px 10px;
        margin-bottom: 4px;
    }
    .t-title {
        font-size: 0.68rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.05em;
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

# --- Sichere Einzel-Karten-Komponente ---
def render_terminal_card(title, value, pct=None, unit=""):
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

    for name, symbol in indices