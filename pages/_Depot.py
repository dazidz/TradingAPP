import streamlit as st
import sqlite3
import pandas as pd

# Sicherheits-Check: Nur Zugriff, wenn bereits auf der Hauptseite eingeloggt
if "password_correct" not in st.session_state or not st.session_state.password_correct:
    st.error("Bitte zuerst auf der Startseite anmelden!")
    st.stop()

# --- SEITENINHALT ---
st.header("📝 Trade Journal")
DB_NAME = 'elite_v5.db'

with st.form("trade_form"):
    col1, col2 = st.columns(2)
    ticker = col1.text_input("Ticker").upper()
    cat = col2.selectbox("Typ", ["Invest", "Swing", "Risiko"])
    qty = col1.number_input("Menge", min_value=0.0)
    price = col2.number_input("Einstandspreis", min_value=0.0)
    
    if st.form_submit_button("Trade Einbuchen"):
        try:
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO trades (ticker, cat, qty, price) VALUES (?, ?, ?, ?)", 
                             (ticker, cat, qty, price))
            st.success("Trade gespeichert.")
        except Exception as e:
            st.error(f"Fehler beim Speichern: {e}")

# Anzeige des Journals
st.subheader("Bisherige Trades")
try:
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql_query("SELECT * FROM trades", conn)
        st.table(df)
except Exception as e:
    st.warning("Konnte Journal nicht laden (Tabelle 'trades' existiert evtl. noch nicht).")