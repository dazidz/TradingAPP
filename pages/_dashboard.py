import streamlit as st
import yfinance as yf
import time

st.header("📊 Executive Dashboard")
MARKETS = {"Indizes": {"SPX": "^GSPC", "NDX": "^IXIC", "DJI": "^DJI", "DAX": "^GDAXI"}}

@st.cache_data(ttl=3600)
def get_ampel_data(ticker):
    # Kurze Pause, um Yahoo nicht zu fluten
    time.sleep(1) 
    try:
        # Timeout und Threading-Optionen zur Stabilisierung
        df = yf.download(ticker, period="30d", interval="1d", progress=False, timeout=5)
        if df.empty: return "⚪"
        close = float(df['Close'].iloc[-1])
        sma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        return "🟢" if close > sma20 else "🔴"
    except Exception as e:
        return f"Fehler: {str(e)[:10]}"

for group, tickers in MARKETS.items():
    st.subheader(group)
    for name, ticker in tickers.items():
        st.metric(name, get_ampel_data(ticker))