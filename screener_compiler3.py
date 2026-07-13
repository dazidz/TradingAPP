import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import time
from db import get_db_client

supabase = get_db_client()

def get_ticker_list_with_names():
    try:
        response = supabase.table("watchlist").select("ticker, company_name, sector, gettex_ticker").execute()
        return [t for t in response.data if t.get('ticker') and str(t['ticker']).strip()]
    except Exception as e:
        print(f"❌ Fehler beim Laden der 'watchlist': {e}")
        return []

def save_to_supabase(ticker, company_name, signal_type, candle_time, sector, gettex_ticker):
    try:
        date_str = datetime.datetime.now(pytz.UTC).strftime('%Y-%m-%d')
        check = supabase.table("signals").select("id").eq("ticker", ticker).gte("created_at", date_str + " 00:00:00").execute()
        if len(check.data) > 0: return 

        data = {
            "ticker": ticker, "company_name": company_name, "signal_type": signal_type,
            "candle_time": candle_time.isoformat(), "sector": sector, "gettex_ticker": gettex_ticker,
            "created_at": datetime.datetime.now(pytz.UTC).isoformat()
        }
        supabase.table("signals").insert(data).execute()
        print(f"✅ {ticker} -> {signal_type}")
    except Exception as e: print(f"❌ Fehler beim Speichern von {ticker}: {e}")

def scan_ticker(ticker_info):
    ticker = ticker_info['ticker']
    data = yf.download(ticker, period="1mo", interval="1h", progress=False, auto_adjust=True)
    
    if data.empty or len(data) < 30: return

    # Hilfsfunktion für TradingView-Style RMA
    def rma(series, length): return series.ewm(alpha=1/length, adjust=False).mean()

    # Preisanpassung (Gettex-Optimierung)
    for col in ['Open', 'High', 'Low', 'Close']:
        if col in data.columns: data[col] = data[col] * 1.016

    high, low, close = data['High'], data['Low'], data['Close']
    
    # ADX Berechnung
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = rma(tr, 14)
    plus_di = 100 * (rma((high - high.shift()).clip(lower=0), 14) / atr)
    minus_di = 100 * (rma((low.shift() - low).clip(lower=0), 14) / atr)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 0.0001)
    adxV = rma(dx, 14)

    # SMI Berechnung (Pine Script 1:1)
    smiL, smiS1, smiS2 = 10, 1, 10
    hi, lo = high.rolling(smiL).max(), low.rolling(smiL).min()
    rel = close - (hi + lo) / 2
    df = hi - lo
    aR = rel.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    aD = df.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    smiV = np.where(aD != 0, (aR / (aD / 2) * 100), 0)
    sigN = pd.Series(smiV).ewm(span=5, adjust=False).mean()

    # Pivot-Logik (suche ta.pivotlow(5, 2))
    smi_s = pd.Series(smiV)
    is_pivot = (smi_s.shift(2) < smi_s.shift(3)) & (smi_s.shift(2) < smi_s.shift(4)) & \
               (smi_s.shift(2) < smi_s.shift(5)) & (smi_s.shift(2) < smi_s.shift(6)) & \
               (smi_s.shift(2) < smi_s.shift(1)) & (smi_s.shift(2) < smi_s)
    
    lSL = pd.Series(np.where(is_pivot, smi_s.shift(2), np.nan), index=data.index).ffill()
    lPL = pd.Series(np.where(is_pivot, low.shift(2), np.nan), index=data.index).ffill()
    
    # Signale
    cUp = (pd.Series(smiV).shift(1) < sigN.shift(1)) & (pd.Series(smiV) > sigN)
    regD = (low < lPL) & (pd.Series(smiV) > lSL) & (pd.Series(smiV) < -40)
    hidD = (low > lPL) & (pd.Series(smiV) < lSL) & (lSL < -20)
    
    sE = (cUp & regD & (adxV > 18)) | (cUp & hidD & (adxV > 25))
    sK = (~sE) & cUp & (pd.Series(smiV) < -35) & ((adxV > 18) | (adxV > adxV.shift(1)))
    
    # Speichern
    if sE.iloc[-1]: save_to_supabase(ticker, ticker_info.get('company_name'), "ELITE", data.index[-1], ticker_info.get('sector'), ticker_info.get('gettex_ticker'))
    elif sK.iloc[-1]: save_to_supabase(ticker, ticker_info.get('company_name'), "KAUFEN", data.index[-1], ticker_info.get('sector'), ticker_info.get('gettex_ticker'))

if __name__ == "__main__":
    ticker_liste = get_ticker_list_with_names()
    for t_info in ticker_liste:
        try:
            scan_ticker(t_info)
            time.sleep(0.1)
        except Exception as e: print(f"❌ Fehler bei {t_info['ticker']}: {e}")