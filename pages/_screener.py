import streamlit as st
import pandas as pd
import sqlite3
import os

# Pfad-Logik: Geht einen Ordner hoch (aus 'pages' raus) zum Hauptordner
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'elite_v5.db')

st.header("💎 Elite Kauf-Signale")

if os.path.exists(DB_PATH):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Überprüfen, ob Tabelle existiert
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signals'")
            if cursor.fetchone():
                df = pd.read_sql_query("SELECT * FROM signals", conn)
                st.table(df)
            else:
                st.warning("Keine Signale gefunden. Bitte 'start.bat' ausführen.")
    except Exception as e:
        st.error(f"Datenbankfehler: {e}")
else:
    st.error(f"Datenbankdatei nicht gefunden unter: {DB_PATH}")