import sqlite3
conn = sqlite3.connect('elite_v5.db')
# Journal: Ticker, Typ, Menge, Preis, Einbuchungsdatum
conn.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, ticker TEXT, cat TEXT, qty REAL, price REAL)")
# Watchliste: Ticker, Name, Status
conn.execute("CREATE TABLE IF NOT EXISTS watchlist (ticker TEXT PRIMARY KEY, name TEXT, status TEXT)")
conn.commit(); conn.close()