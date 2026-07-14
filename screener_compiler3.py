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
    
    # Download
    data = yf.download(ticker, period="5d", interval="1h", progress=False, auto_adjust=True)
    if data.empty or len(data) < 20: return

    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
    data.columns = [str(c).lower() for c in data.columns]
    
    # Preisanpassung
    for col in ['open', 'high', 'low', 'close']:
        if col in data.columns: data[col] = data[col] * 1.016
    
    high, low, close = data['high'], data['low'], data['close']
    
    # 1. Indikatoren - RMA Funktion
    def rma(series, length): return series.ewm(alpha=1/length, adjust=False).mean()
    
    # 2. ADX (Ohne 1.25 Faktor!)
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = rma(tr, 14)
    plus_di = 100 * (rma((high - high.shift()).clip(lower=0), 14) / atr)
    minus_di = 100 * (rma((low.shift() - low).clip(lower=0), 14) / atr)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 0.0001)
    adxV = rma(dx, 14) # Standard ADX
    
    # 3. SMI
    smiL, smiS1, smiS2, sigL = 10, 3, 10, 5
    hi, lo = high.rolling(smiL).max(), low.rolling(smiL).min()
    diff, rdiff = hi - lo, close - (hi + lo) / 2
    aR = rdiff.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    aD = diff.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    smiV = pd.Series(np.where(aD != 0, (aR / (aD / 2) * 100), 0), index=data.index).rolling(5).mean()
    sigN = smiV.ewm(span=sigL, adjust=False).mean()

    # 4. PIVOT & SIGNALE
    is_pivot = (smiV.shift(2) < smiV.shift(3)) & (smiV.shift(2) < smiV.shift(4)) & (smiV.shift(2) < smiV.shift(5)) & (smiV.shift(2) < smiV.shift(6)) & (smiV.shift(2) < smiV.shift(7)) & (smiV.shift(2) < smiV.shift(1)) & (smiV.shift(2) < smiV)
    lSL = pd.Series(np.where(is_pivot, smiV.shift(2), np.nan), index=data.index).ffill()
    lPL = pd.Series(np.where(is_pivot, low.shift(2), np.nan), index=data.index).ffill()
    
    cUp = (smiV.shift(1) < sigN.shift(1)) & (smiV > sigN)
    regD = (low < lPL) & (smiV > lSL) & (smiV < -20) # Gelockert von -40 auf -20
    hidD = (low > lPL) & (smiV < lSL) & (lSL < -10)  # Gelockert von -20 auf -10
    
    # ELITE: ADX Filter nun "realistischer" (18 und 25)
    sE = (cUp & regD & (adxV > 10)) | (cUp & hidD & (adxV > 15))
    sK = (~sE) & cUp & (smiV < -25) & ((adxV > 10) | (adxV > adxV.shift(1)))
    
    # Speichern der aktuellsten Kerze (bei Bedarf auf alle Kerzen ausweiten)
    if sE.iloc[-1]: 
        print(f"✨ Elite Signal bei {ticker}!")
        save_to_supabase(ticker, name, "ELITE", data.index[-1], sector, gettex_ticker)
    elif sK.iloc[-1]: 
        print(f"📈 Kaufen Signal bei {ticker}!")
        save_to_supabase(ticker, name, "KAUFEN", data.index[-1], sector, gettex_ticker)


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