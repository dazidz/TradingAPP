import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import time
from db import get_db_client

supabase = get_db_client()

def get_ticker_list_from_db():
    try:
        response = supabase.table("watchlist").select("ticker").execute()
        return [item['ticker'] for item in response.data]
    except Exception as e:
        print(f"❌ Fehler bei DB-Abfrage: {e}")
        return []

def save_to_supabase(ticker, signal_type, timestamp):
    try:
        date_str = timestamp.strftime('%Y-%m-%d')
        check = supabase.table("signals").select("id").eq("ticker", ticker).gte("created_at", date_str + " 00:00:00").execute()
        if len(check.data) > 0: return 
        
        data = {"ticker": ticker, "signal_type": signal_type, "strength": 1, "created_at": timestamp.isoformat()}
        supabase.table("signals").insert(data).execute()
        print(f"✅ {ticker} -> Signal in DB gespeichert ({signal_type})")
    except Exception as e:
        print(f"❌ Fehler beim Speichern: {e}")

def scan_ticker(ticker):
    data = yf.download(ticker, period="5d", interval="1h", progress=False, auto_adjust=True)
    
    # Robustes Flattening
    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
    data.columns = [str(c).lower() for c in data.columns]
    
    if data.empty or not all(col in data.columns for col in ['open', 'high', 'low', 'close']):
        print(f"❌ {ticker}: Keine Daten.")
        return
    
    # GETTEX-ADAPTER
    for col in ['open', 'high', 'low', 'close']: data[col] = data[col] * 1.016
    
    # Indikatoren-Berechnung
    smiL, smiS1, smiS2, sigL, adxL, adxM = 10, 1, 10, 5, 14, 18
    hi, lo = data['high'].rolling(smiL).max(), data['low'].rolling(smiL).min()
    rel = data['close'] - (hi + lo) / 2
    aR = rel.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    aD = (hi - lo).ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    smiV = pd.Series(np.where(aD != 0, (aR / (aD / 2) * 100), 0), index=data.index)
    sigN = smiV.ewm(span=sigL, adjust=False).mean()
    
    tr = pd.concat([data['high'] - data['low'], abs(data['high'] - data['close'].shift()), abs(data['low'] - data['close'].shift())], axis=1).max(axis=1)
    atr = tr.rolling(adxL).mean()
    plus_di = 100 * (data['high'].diff().clip(lower=0)).rolling(adxL).mean() / atr
    minus_di = 100 * (data['low'].diff().shift().clip(lower=0)).rolling(adxL).mean() / atr
    adxV = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)

    # DEBUG AUSGABE FÜR DICH
    print(f"\n--- DEBUG: {ticker} (Letzte 10 Stunden) ---")
    for i in range(1, 11):
        idx = -i
        print(f"Zeit: {data.index[idx].strftime('%d.%m. %H:%M')} | SMI: {smiV.iloc[idx]:.2f} | ADX: {adxV.iloc[idx]:.2f}")

    # Signallogik
    is_pivot = (smiV.shift(2) < smiV.shift(3)) & (smiV.shift(2) < smiV.shift(4)) & (smiV.shift(2) < smiV.shift(1)) & (smiV.shift(2) < smiV)
    lSL = pd.Series(np.where(is_pivot, smiV.shift(2), np.nan), index=data.index).ffill()
    lPL = pd.Series(np.where(is_pivot, data['low'].shift(2), np.nan), index=data.index).ffill()
    cUp = (smiV.shift(1) < sigN.shift(1)) & (smiV > sigN)
    regD = (data['low'] < lPL) & (smiV > lSL) & (smiV < -40)
    
    start_index = max(0, len(data) - 24)
    found = False
    for i in range(start_index, len(data)):
        if (cUp & regD & (adxV > adxM)).iloc[i]:
            save_to_supabase(ticker, "ELITE", data.index[i])
            print(f"🔥 {ticker}: ELITE-Signal am {data.index[i]}")
            found = True
            break
    if not found: print(f"ℹ️ {ticker}: Kein Signal.")

if __name__ == "__main__":
    for ticker in get_ticker_list_from_db():
        try:
            scan_ticker(ticker)
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ Fehler bei {ticker}: {e}")