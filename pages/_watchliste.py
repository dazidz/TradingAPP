import yfinance as yf
import sqlite3

def verify_ticker(ticker_symbol):
    """
    Prüft bei Yahoo, ob der Ticker existiert.
    Gibt (True, TickerName) zurück, oder (False, None).
    """
    try:
        t = yf.Ticker(ticker_symbol)
        info = t.info
        # 'longName' ist der offizielle Firmenname bei Yahoo
        name = info.get('longName', 'Unbekannt')
        # Ein kleiner Test-Call: Wenn 'symbol' fehlt, ist der Ticker Müll
        if 'symbol' in info:
            return True, name
        return False, None
    except Exception:
        return False, None

def add_ticker_to_db(ticker_symbol):
    valid, name = verify_ticker(ticker_symbol)
    if valid:
        # Hier erfolgt das INSERT in deine SQLite-Datenbank
        # ... SQL Logic ...
        print(f"✅ Hinzugefügt: {ticker_symbol} ({name})")
        return True, name
    else:
        print(f"❌ Fehler: {ticker_symbol} konnte nicht verifiziert werden.")
        return False, None