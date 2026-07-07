import yfinance as yf
import pandas as pd

signals = [
    ("QCOM", "2026-07-01 13:00:00"),
    ("MCHP", "2026-07-02 22:00:00"),
    ("AVGO", "2026-07-03 08:00:00"),
    ("BMW.DE", "2026-06-29 21:00:00"),
    ("HIMX", "2026-07-02 15:00:00")
]

for ticker, t_time in signals:
    df = yf.download(ticker, period="5d", interval="1h", progress=False)
    # Entferne MultiIndex falls vorhanden
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    # Prüfe ob Zeit existiert
    if t_time in df.index:
        row = df.loc[t_time]
        print(f"{ticker} | YF-Close: {row['close'].iloc[0]:.2f} | YF-Low: {row['low'].iloc[0]:.2f}")
    else:
        print(f"{ticker} | Zeitpunkt {t_time} nicht in Yahoo-Daten gefunden.")