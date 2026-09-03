import streamlit as st
from supabase import create_client
import pandas as pd
import yfinance as yf

st.set_page_config(layout="wide", page_title="VisionDZ - Teamroom", page_icon="🏢")

# Sicherheitsprüfung (Login-Status übernehmen)
if not st.session_state.get("password_correct", False):
    st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
    st.stop()

# Supabase Verbindung
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

st.title("🏢 VisionDZ - Teamroom")
st.markdown("Willkommen in der Kommandozentrale. Hier triffst du dich mit deinen KI-Mitarbeitern zum Daily Standup.")

# Mitarbeiter-Auswahl
st.sidebar.markdown("### 🤖 KI-Mitarbeiter")
selected_employee = st.sidebar.selectbox("Mitarbeiter wählen:", ["Otto (History Analyst)"])

st.divider()

if selected_employee == "Otto (History Analyst)":
    st.subheader("📊 Otto – History & Market Analyst")
    st.caption("Zuständig für historische Muster, Marktphasen und datenbasierte Briefings.")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("#### 📝 Tägliche Analyse & Gedächtnis")
        
        # Button, um Otto eine neue Analyse schreiben zu lassen
        if st.button("🚀 Otto: Neuen Tagesbericht erstellen & speichern"):
            with st.spinner("Otto analysiert die Historie..."):
                try:
                    # Einfache Marktdaten holen für die Analyse
                    df_spy = yf.download("^GSPC", period="5d", progress=False)
                    current_val = float(df_spy['Close'].iloc[-1])
                    prev_val = float(df_spy['Close'].iloc[-2])
                    change = ((current_val - prev_val) / prev_val) * 100
                    
                    phase = "Bullenmarkt / Aufwärtstrend" if change > 0 else "Konsolidierung / Druck"
                    insight_text = f"S&P 500 steht bei {current_val:,.2f} ({change:+.2f}%). Historische Muster deuten auf eine Phase der {phase} hin."
                    
                    # In Ottos eigene Tabelle speichern
                    supabase.table("employee_otto_memory").insert({
                        "market_phase": phase,
                        "insight": insight_text
                    }).execute()
                    
                    st.success("Otto hat seinen Bericht erfolgreich im Langzeitgedächtnis hinterlegt!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Fehler bei Ottos Analyse: {e}")
        
        # Bisherige Einträge aus Ottos Gedächtnis laden
        try:
            response = supabase.table("employee_otto_memory").select("*").order("analysis_date", desc=True).limit(5).execute()
            logs = response.data
            
            if logs:
                st.markdown("### 📚 Ottos Logbuch (Letzte Einträge)")
                for log in logs:
                    with st.expander(f"Bericht vom {log['analysis_date']} – Phase: {log['market_phase']}"):
                        st.write(log['insight'])
                        if log.get('user_feedback'):
                            st.info(f"Dein Feedback: {log['user_feedback']}")
            else:
                st.info("Noch keine Einträge in Ottos Gedächtnis vorhanden. Starte oben die erste Analyse.")
        except Exception as e:
            st.error(get_error_msg(e))

    with col2:
        st.markdown("#### 💬 Direkt mit Otto sprechen")
        st.markdown("Gib Otto Anweisungen oder Feedback für seine nächste Analyse:")
        
        user_input = st.text_area("Nachricht an Otto:", placeholder="Z.B.: 'Otto, konzentriere dich morgen stärker auf den Technologiesektor.'")
        if st.button("Anweisung senden"):
            if user_input:
                try:
                    # Letzten Log holen und Feedback speichern
                    res = supabase.table("employee_otto_memory").select("id").order("analysis_date", desc=True).limit(1).execute()
                    if res.data:
                        latest_id = res.data[0]['id']
                        supabase.table("employee_otto_memory").update({"user_feedback": user_input}).eq("id", latest_id).execute()
                        st.success("Anweisung an Otto übergeben und gespeichert!")
                    else:
                        st.warning("Kein Bericht vorhanden, an den das Feedback angehängt werden kann.")
                except Exception as e:
                    st.error(f"Fehler: {e}")
            else:
                st.warning("Bitte gib eine Nachricht ein.")

def get_error_msg(e):
    return f"Datenbank-Fehler: {e}"