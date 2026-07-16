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

def save_to_supabase(ticker, company_name, signal_type, candle_time, sector, gettex_ticker, meta_data, entry_price):
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
            "entry_price": float(entry_price),
            "created_at": datetime.datetime.now(pytz.UTC).isoformat(),
            "meta_data": str(meta_data) # Speichert die Werte als String/JSON
        }
        supabase.table("signals").insert(data).execute()
        print(f"✅ {ticker} -> {signal_type} gespeichert (Meta: {meta_data})")
    except Exception as e:
        print(f"❌ Fehler beim Speichern von {ticker}: {e}")

def scan_ticker(ticker_info):
    ticker = ticker_info['ticker']
    name = ticker_info.get('company_name', 'N/A')
    sector = ticker_info.get('sector', 'N/A')
    gettex_ticker = ticker_info.get('gettex_ticker', '')
    
    
    data = yf.download(ticker, period="3mo", interval="1h", progress=False, auto_adjust=True)
    
    if data.empty or len(data) < 20:
        print(f"⚠️ {ticker}: Zu wenig Daten.")
        return

    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
    data.columns = [str(c).lower() for c in data.columns]
    
    # Preisanpassung
    for col in ['open', 'high', 'low', 'close']:
        if col in data.columns: data[col] = data[col] * 1.016
    
    high, low, close = data['high'], data['low'], data['close']
    
    # --- INDIKATOREN & SCORING LOGIK ---

    # ADX Berechnung
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    def rma(series, length): return series.ewm(alpha=1/length, adjust=False).mean()
    atr = rma(tr, 14)
    plus_di = 100 * (rma((high - high.shift()).clip(lower=0), 14) / atr)
    minus_di = 100 * (rma((low.shift() - low).clip(lower=0), 14) / atr)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 0.0001)
    adxV = rma(dx, 14)
    
    # Indikatoren-Berechnung
   # --- 2. Indikatoren & PIVOT LOGIK (Exakt wie Pine Script) ---
    smiL, smiS1, smiS2, sigL = 10, 3, 10, 5
    hi, lo = high.rolling(smiL).max(), low.rolling(smiL).min()
    diff, rdiff = hi - lo, close - (hi + lo) / 2
    
    # EMAs für Stabilität
    aR = rdiff.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    aD = diff.ewm(span=smiS1, adjust=False).mean().ewm(span=smiS2, adjust=False).mean()
    
    # SMI normalisiert
    smiV = pd.Series(np.where(aD != 0, (aR / (aD / 2) * 100), 0), index=data.index)
    sigN = smiV.ewm(span=sigL, adjust=False).mean()

    # Korrekte Pivot-Logik (ta.pivotlow Simulation)
    # Wir schauen auf die Kerze 'i-2' als potenzielles Tief
    smiV_s = smiV.shift(2)
    is_pivot = (smiV_s < smiV.shift(3)) & (smiV_s < smiV.shift(4)) & \
               (smiV_s < smiV.shift(1)) & (smiV_s < smiV)
    
    # Pivot-Werte festschreiben
    lSL = pd.Series(np.where(is_pivot, smiV_s, np.nan), index=data.index).ffill()
    lPL = pd.Series(np.where(is_pivot, low.shift(2), np.nan), index=data.index).ffill()

    # --- 3. Strikte Signal-Logik ---
    cUp = (smiV.shift(1) < sigN.shift(1)) & (smiV > sigN)
    
    # Divergenz-Bedingungen aus Pine
    regD = (low < lPL) & (smiV > lSL) & (smiV < -40)
    hidD = (low > lPL) & (smiV < lSL) & (lSL < -20)
    
    # ELITE & KAUFEN
    is_elite = cUp & (regD | hidD) & (adxV > 18)
    is_buy = (~is_elite) & cUp & (smiV < -35) & (adxV > 18)

    # --- 4. Signal-Suche (Mit 5-Tage-Filter) ---
    signal_found = False
    heute = pd.Timestamp.now(tz='UTC')
    
    # Wir gehen rückwärts durch die Daten
    for i in reversed(range(len(data))):
        candle_time = data.index[i].tz_localize(None).tz_localize('UTC') # Sicherstellung UTC
        
        # Stopp, wenn Signal älter als 5 Tage
        if (heute - candle_time).days > 5:
            break
            
        meta = {"smi": round(float(smiV.iloc[i]), 2), "adx": round(float(adxV.iloc[i]), 2)}
        
        if is_elite.iloc[i]:
            current_price = data['close'].iloc[i]
            save_to_supabase(ticker, name, "ELITE", candle_time, sector, gettex_ticker, meta)
            signal_found = True
            break # Nur das aktuellste Signal pro Ticker speichern
        elif is_buy.iloc[i]:
            current_price = data['close'].iloc[i]
            save_to_supabase(ticker, name, "KAUFEN", candle_time, sector, gettex_ticker, meta)
            signal_found = True
            break
            
    if not signal_found:
        print(f"ℹ️ {ticker}: Kein Signal.")

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