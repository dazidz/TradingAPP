import yfinance as yf
import pandas as pd
import numpy as np

# Deine Daten... (bleibt gleich)
referenz_liste = [
    {"ticker": "NVDA", "time": "2026-05-06 13:00", "adx_tv": 31.44, "smi_tv": -20.22},
    {"ticker": "MSFT", "time": "2026-02-24 13:00", "adx_tv": 31.00, "smi_tv": -65.53},
    {"ticker": "AVGO", "time": "2026-03-31 07:30", "adx_tv": 44.53, "smi_tv": -57.58},
    {"ticker": "TSLA", "time": "2026-06-11 13:00", "adx_tv": 29.57, "smi_tv": -45.33},
    {"ticker": "TSLA", "time": "2026-06-26 15:00", "adx_tv": 33.18, "smi_tv": -48.78},
    {"ticker": "WMT", "time": "2025-08-26 19:00", "adx_tv": 27.41, "smi_tv": -61.96},
    {"ticker": "JPM", "time": "2026-03-30 11:00", "adx_tv": 26.96, "smi_tv": -73.44},
    {"ticker": "INTC", "time": "2026-03-30 11:00", "adx_tv": 29.50, "smi_tv": -58.67},
    {"ticker": "JNJ", "time": "2026-05-11 21:00", "adx_tv": 22.15, "smi_tv": -48.59},
    {"ticker": "JNJ", "time": "2026-01-12 15:00", "adx_tv": 17.64, "smi_tv": -48.84},
    {"ticker": "CAT", "time": "2026-04-16 19:00", "adx_tv": 36.51, "smi_tv": -28.76},
    {"ticker": "ABBV", "time": "2026-05-11 07:30", "adx_tv": 28.86, "smi_tv": -48.29},
    {"ticker": "ORCL", "time": "2026-04-10 15:00", "adx_tv": 33.52, "smi_tv": -62.45},
    {"ticker": "ORCL", "time": "2025-09-02 09:00", "adx_tv": 37.44, "smi_tv": -39.25},
    {"ticker": "HD", "time": "2026-05-18 15:00", "adx_tv": 38.32, "smi_tv": -53.03},
    {"ticker": "GEV", "time": "2026-03-31 15:00", "adx_tv": 23.60, "smi_tv": -58.94},
    {"ticker": "PLTR", "time": "2026-04-10 15:00", "adx_tv": 43.56, "smi_tv": -72.59},
    {"ticker": "PLTR", "time": "2026-05-07 15:00", "adx_tv": 34.03, "smi_tv": -49.18},
    {"ticker": "IBM", "time": "2026-05-13 21:00", "adx_tv": 49.47, "smi_tv": -72.28},
    {"ticker": "IBM", "time": "2026-04-13 17:00", "adx_tv": 33.09, "smi_tv": -68.71},
]

def get_indicators(data):
    high, low, close = data['high'], data['low'], data['close']
    tr = pd.concat([high-low, abs(high-close.shift()), abs(low-close.shift())], axis=1).max(axis=1)
    def rma(s, l): return s.ewm(alpha=1/l, adjust=False).mean()
    atr = rma(tr, 14)
    plus = 100 * (rma((high-high.shift()).clip(0), 14) / atr)
    minus = 100 * (rma((low.shift()-low).clip(0), 14) / atr)
    adx = 100 * rma(abs(plus-minus) / (plus+minus).replace(0, 0.0001), 14)
    hi, lo = high.rolling(10).max(), low.rolling(10).min()
    diff, rdiff = hi-lo, close-(hi+lo)/2
    smi = pd.Series(np.where(diff!=0, (rdiff.ewm(span=1, adjust=False).mean().ewm(span=10, adjust=False).mean() / (diff.ewm(span=1, adjust=False).mean().ewm(span=10, adjust=False).mean() / 2) * 100), 0), index=data.index).rolling(5).mean()
    return adx, smi

print(f"{'Ticker':<6} | {'Zeit':<16} | {'ADX TV':<8} | {'ADX Yahoo':<10} | {'SMI TV':<8} | {'SMI Yahoo':<10}")
print("-" * 85)

for ref in referenz_liste:
    data = yf.download(ref['ticker'], period="2y", interval="1h", progress=False, auto_adjust=True)
    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
    data.columns = [str(c).lower() for c in data.columns]
    for col in ['high', 'low', 'close']: 
        if col in data.columns: data[col] = data[col] * 1.016
    
    adx, smi = get_indicators(data)
    
    # FIX: Zeitstempel auf UTC/New_York normalisieren
    t = pd.to_datetime(ref['time']).tz_localize('America/New_York')
    
    idx_list = data.index.get_indexer([t], method='nearest')
    idx = idx_list[0]
    
    print(f"{ref['ticker']:<6} | {ref['time']:<16} | {ref['adx_tv']:<8} | {adx.iloc[idx]:<10.2f} | {ref['smi_tv']:<8} | {smi.iloc[idx]:<10.2f}")