import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import time
from db import get_db_client

# Verbindung zur DB
supabase = get_db_client()

def get_ticker_list_from_db():
    try:
        # Tabellenname ist wieder "watchlist"
        response = supabase.table("watchlist").select("ticker").execute()
        return [item['ticker'] for item in response.data]
    except Exception as e:
        print(f"❌ Fehler beim Laden der 'watchlist': {e}")
        return []

def save_to_supabase(ticker, signal_type, timestamp):
    try:
        date_str = timestamp.strftime('%Y-%m-%d')
        check = supabase.table("signals").select("id") \
            .eq("ticker", ticker) \
            .gte("created_at", date_str + " 00:00:00") \
            .execute()
        
        if len(check.data) > 0:
            return 

        data = {
            "ticker": ticker,
            "signal_type": signal_type,
            "strength": 1,
            "created_at": timestamp.isoformat()
        }
        supabase.table("signals").insert(data).execute()
        print(f"✅ {ticker} -> Signal in DB gespeichert ({signal_type})")
    except Exception as e:
        print(f"❌ Fehler beim Speichern von {ticker}: {e}")

def scan_ticker(ticker):
    print(f"🔍 Prüfe: {ticker}...")
    
    # 1. Daten laden
    data = yf.download(ticker, period="5d", interval="1h", progress=False, auto_adjust=True)
    
    if data.empty:
        print(f"❌ {ticker}: Keine Daten gefunden.")
        return
    
    if len(data) < 20:
        print(f"⚠️ {ticker}: Zu wenig Daten ({len(data)}), überspringe.")
        return

    # 2. Struktur-Bereinigung
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data.columns = [str(c).lower() for c in data.columns]
    
    # 3. GETTEX-ADAPTER (OFFSET 1.6%)
    for col in ['open', 'high', 'low', 'close']:
        if col in data.columns:
            data[col] = data[col] * 1.016
    
    # 4. Indikatoren-Berechnung (EliteV4)
    smiL, smiS1, smiS2, sigL, adxL, adxM = 10, 1, 10, 5, 14, 18
    hi = data['high'].rolling(smiL).max()
    lo = data['low'].rolling(smiL).min()
    rel = data['close'] - (hi + lo) / 2
    df_range = hi - lo
    aR = rel.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    aD = df_range.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    smiV = np.where(aD != 0, (aR / (aD / 2) * 100), 0)
    smiV = pd.Series(smiV, index=data.index)
    sigN = smiV.ewm(span=sigL, adjust=False).mean()

    tr = pd.concat([data['high'] - data['low'], abs(data['high'] - data['close'].shift()), abs(data['low'] - data['close'].shift())], axis=1).max(axis=1)
    atr = tr.rolling(adxL).mean()
    plus_di = 100 * (data['high'].diff().clip(lower=0)).rolling(adxL).mean() / atr
    minus_di = 100 * (data['low'].diff().shift().clip(lower=0)).rolling(adxL).mean() / atr
    adxV = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    
    is_pivot = (smiV.shift(2) < smiV.shift(3)) & (smiV.shift(2) < smiV.shift(4)) & (smiV.shift(2) < smiV.shift(5)) & (smiV.shift(2) < smiV.shift(6)) & (smiV.shift(2) < smiV.shift(7)) & (smiV.shift(2) < smiV.shift(1)) & (smiV.shift(2) < smiV)
    lSL = pd.Series(np.where(is_pivot, smiV.shift(2), np.nan), index=data.index).ffill()
    lPL = pd.Series(np.where(is_pivot, data['low'].shift(2), np.nan), index=data.index).ffill()
    
    cUp = (smiV.shift(1) < sigN.shift(1)) & (smiV > sigN)
    regD = (data['low'] < lPL) & (smiV > lSL) & (smiV < -40)
    hidD = (data['low'] > lPL) & (smiV < lSL) & (lSL < -20)
    
    sE = (cUp & regD & (adxV > adxM)) | (cUp & hidD & (adxV > 25))
    sK = (~sE) & cUp & (smiV < -35) & ((adxV > adxM) | (adxV > adxV.shift(1)))
    
    # 5. Scan-Logik
    start_index = max(0, len(data) - 5)
    signal_found = False
    
    for i in range(start_index, len(data)):
        if sE.iloc[i]:
            save_to_supabase(ticker, "ELITE", data.index[i])
            print(f"🔥 {ticker}: ELITE-Signal gefunden!")
            signal_found = True
        elif sK.iloc[i]:
            save_to_supabase(ticker, "KAUFEN", data.index[i])
            print(f"💰 {ticker}: KAUFEN-Signal gefunden!")
            signal_found = True
            
    if not signal_found:
        print(f"ℹ️ {ticker}: Kein Signal.")

if __name__ == "__main__":
    print("🧹 Bereinige alte Signale (>48h)...")
    try:
        cutoff = (datetime.datetime.now(pytz.UTC) - datetime.timedelta(hours=48)).isoformat()
        supabase.table("signals").delete().lt("created_at", cutoff).execute()
        print("✅ Bereinigung fertig.")
    except Exception as e:
        print(f"❌ Fehler bei der Bereinigung: {e}")

    print("🚀 Starte Batch-Scan...")
    ticker_liste = get_ticker_list_from_db()
    
    if not ticker_liste:
        print("⚠️ Keine Ticker in 'watchlist' gefunden.")
    else:
        print(f"📦 Ticker geladen: {ticker_liste}")
        for ticker in ticker_liste:
            try:
                scan_ticker(ticker)
                time.sleep(0.5)
            except Exception as e:
                print(f"❌ Kritischer Fehler bei {ticker}: {e}")
        print("🏁 Scan abgeschlossen.")