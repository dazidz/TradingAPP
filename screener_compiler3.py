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
        response = supabase.table("watchlist").select("ticker, company_name, sector, gettex_ticker").execute()
        return response.data 
    except Exception as e:
        print(f"❌ Fehler beim Laden der 'watchlist': {e}")
        return []

def save_to_supabase(ticker, company_name, signal_type, candle_time, sector, gettex_ticker):
    try:
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
    
    # 1. Daten laden
    data = yf.download(ticker, period="5d", interval="1h", progress=False, auto_adjust=True)
    
    # Sicherstellung, dass wir genug Daten haben
    if data.empty or len(data) < 20:
        return

    # MultiIndex Fix für moderne yfinance Versionen
    if isinstance(data.columns, pd.MultiIndex): 
        data.columns = data.columns.get_level_values(0)
    data.columns = [str(c).lower() for c in data.columns]
    
    # Preisanpassung
    for col in ['open', 'high', 'low', 'close']:
        if col in data.columns: 
            # Fix für ndarray Probleme: .squeeze() erzwingt 1D-Format
            data[col] = data[col].squeeze() * 1.016
    
    high, low, close = data['high'], data['low'], data['close']
    
    # --- OPTIMIERTER INDIKATOR-BLOCK ---
    def rma(series, length): return series.ewm(alpha=1/length, adjust=False).mean()
    
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = rma(tr, 14)
    plus_di = 100 * (rma((high - high.shift()).clip(lower=0), 14) / atr)
    minus_di = 100 * (rma((low.shift() - low).clip(lower=0), 14) / atr)
    
    # 1. OPTIMIERUNG: Echter ADX ohne künstliche Multiplikation
    adxV = 100 * rma(abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 0.0001), 14)
    
    smiL, smiS1, smiS2, sigL = 10, 3, 10, 5
    hi, lo = high.rolling(smiL).max(), low.rolling(smiL).min()
    diff, rdiff = hi - lo, close - (hi + lo) / 2
    aR = rdiff.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    aD = diff.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    smiV = pd.Series(np.where(aD != 0, (aR / (aD / 2) * 100), 0), index=data.index).rolling(5).mean()
    sigN = smiV.ewm(span=sigL, adjust=False).mean()

    is_pivot = (smiV.shift(2) < smiV.shift(3)) & (smiV.shift(2) < smiV.shift(4)) & (smiV.shift(2) < smiV.shift(5)) & (smiV.shift(2) < smiV.shift(6)) & (smiV.shift(2) < smiV.shift(7)) & (smiV.shift(2) < smiV.shift(1)) & (smiV.shift(2) < smiV)
    lSL = pd.Series(np.where(is_pivot, smiV.shift(2), np.nan), index=data.index).ffill()
    lPL = pd.Series(np.where(is_pivot, low.shift(2), np.nan), index=data.index).ffill()
    
    cUp = (smiV.shift(1) < sigN.shift(1)) & (smiV > sigN)
    
    # 2. OPTIMIERUNG: Schwellenwerte für Divergenz und Trend etwas gelockert
    regD = (low < lPL) & (smiV > lSL) & (smiV < -25) 
    hidD = (low > lPL) & (smiV < lSL) & (lSL < -15)
    
    # 3. OPTIMIERUNG: Angepasste ADX-Schwellen auf den "echten" ADX
    sE = (cUp & regD & (adxV > 12)) | (cUp & hidD & (adxV > 18))
    sK = (~sE) & cUp & (smiV < -30) & ((adxV > 12) | (adxV > adxV.shift(1)))
    
    # SIGNAL_FOUND INITIALISIERUNG
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
            
    if not signal_found:
        pass # Signal-Logik beendet

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
        except Exception as e: print(f"❌ Fehler bei {t_info.get('ticker')}: {e}")
    print("🏁 Scan abgeschlossen.")