import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import time
from db import get_db_client

# Verbindung zur DB
supabase = get_db_client()

def get_ticker_list_with_names():
    try:
        # Lädt Ticker, Name, Sektor und Gettex-Ticker aus der Watchlist
        response = supabase.table("watchlist").select("ticker, company_name, sector, gettex_ticker").execute()
        return response.data 
    except Exception as e:
        print(f"❌ Fehler beim Laden der 'watchlist': {e}")
        return []

def save_to_supabase(ticker, company_name, signal_type, candle_time, sector, gettex_ticker):
    try:
        # Prüfen, ob für diesen Ticker heute schon ein Signal existiert
        date_str = datetime.datetime.now(pytz.UTC).strftime('%Y-%m-%d')
        check = supabase.table("signals").select("id") \
            .eq("ticker", ticker) \
            .gte("created_at", date_str + " 00:00:00") \
            .execute()
        
        if len(check.data) > 0: return 

        data = {
            "ticker": ticker,
            "company_name": company_name,
            "signal_type": signal_type,
            "candle_time": candle_time.isoformat(),
            "sector": sector,
            "gettex_ticker": gettex_ticker,
            "created_at": datetime.datetime.now(pytz.UTC).isoformat()
        }
        supabase.table("signals").insert(data).execute()
        print(f"✅ {ticker} ({company_name}) -> Signal gespeichert: {signal_type}")
    except Exception as e:
        print(f"❌ Fehler beim Speichern von {ticker}: {e}")

def scan_ticker(ticker_info):
    ticker = ticker_info['ticker']
    name = ticker_info.get('company_name', 'N/A')
    sector = ticker_info.get('sector', 'N/A')
    gettex_ticker = ticker_info.get('gettex_ticker', '')
    
    print(f"DEBUG: Ticker={ticker}, Sector={sector}, Gettex={gettex_ticker}")
    
    data = yf.download(ticker, period="10d", interval="1h", progress=False, auto_adjust=True)
    
    if data.empty or len(data) < 20:
        print(f"⚠️ {ticker}: Zu wenig Daten.")
        return

    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
    data.columns = [str(c).lower() for c in data.columns]
    
    # Preisanpassung (wie im Original)
    for col in ['open', 'high', 'low', 'close']:
        if col in data.columns: data[col] = data[col] * 1.016
    
    high, low, close = data['high'], data['low'], data['close']
    
    # Indikatoren
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    def rma(series, length): return series.ewm(alpha=1/length, adjust=False).mean()
    atr = rma(tr, 14)
    plus_di = 100 * (rma((high - high.shift()).clip(lower=0), 14) / atr)
    minus_di = 100 * (rma((low.shift() - low).clip(lower=0), 14) / atr)
    adxV = 100 * rma(abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 0.0001), 14) * 1.25
    
    smiL, smiS1, smiS2, sigL = 10, 3, 10, 5
    hi, lo = high.rolling(smiL).max(), low.rolling(smiL).min()
    diff, rdiff = hi - lo, close - (hi + lo) / 2
    aR = rdiff.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    aD = diff.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    smiV = pd.Series(np.where(aD != 0, (aR / (aD / 2) * 100), 0), index=data.index).rolling(5).mean()
    sigN = smiV.ewm(span=sigL, adjust=False).mean()

    is_pivot = (smiV.shift(2) < smiV.shift(3)) & (smiV.shift(2) < smiV.shift(4)) & (smiV.shift(2) < smiV.shift(5)) & (smiV.shift(2) < smiV.shift(6)) & (smiV.shift(2) < smiV.shift(7)) & (smiV.shift(2) < smiV.shift(1)) & (smiV.shift(2) < smiV)
    lSL = pd.Series(np.where(is_pivot, smiV.shift(2), np.nan), index=data.index).ffill()
    lPL = pd.Series(np.where(is_pivot, data['low'].shift(2), np.nan), index=data.index).ffill()
    
    cUp = (smiV.shift(1) < sigN.shift(1)) & (smiV > sigN)
    regD = (data['low'] < lPL) & (smiV > lSL) & (smiV < -40)
    hidD = (data['low'] > lPL) & (smiV < lSL) & (lSL < -20)
    
    sE = (cUp & regD & (adxV > 18)) | (cUp & hidD & (adxV > 25))
    sK = (~sE) & cUp & (smiV < -35) & ((adxV > 18) | (adxV > adxV.shift(1)))
    
    signal_found = False
    for i in reversed(range(len(data))):
        if sE.iloc[i]:
            save_to_supabase(ticker, name, "ELITE", data.index[i], sector, gettex_ticker)
            signal_found = True
            break
        elif sK.iloc[i]:
            save_to_supabase(ticker, name, "KAUFEN", data.index[i], sector, gettex_ticker)
            signal_found = True
            break
            
    if not signal_found: print(f"ℹ️ {ticker}: Kein Signal.")

if __name__ == "__main__":
    print("🧹 Bereinige alte Signale...")
    try:
        cutoff = (datetime.datetime.now(pytz.UTC) - datetime.timedelta(hours=48)).isoformat()
        supabase.table("signals").delete().lt("created_at", cutoff).execute()
    except Exception as e: print(f"❌ Fehler bei der Bereinigung: {e}")

    print("🚀 Starte Batch-Scan...")
    ticker_liste = get_ticker_list_with_names()
    for t_info in ticker_liste:
        try:
            scan_ticker(t_info)
            time.sleep(0.5)
        except Exception as e: print(f"❌ Fehler bei {t_info['ticker']}: {e}")
    print("🏁 Scan abgeschlossen.")