import sys
from pathlib import Path
import pandas as pd

# Setzt das Hauptverzeichnis fest in den Suchpfad von Python
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

import streamlit as st
from supabase import create_client

# Importiere die Mitarbeiter-Klassen
from employees.otto import OttoAnalyst
from employees.nino import NinoSignalsAssistant

st.set_page_config(layout="wide", page_title="VisionDZ - Team & Kommandozentrale", page_icon="🏢")

if not st.session_state.get("password_correct", False):
    st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
    st.stop()

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# Mitarbeiter-Instanzen erzeugen
otto = OttoAnalyst(supabase)
nino = NinoSignalsAssistant(supabase)

st.title("🏢 VisionDZ - Team & Kommandozentrale")

# --- DIE TABS DEFINIEREN ---
tab_teamroom, tab_otto, tab_nino = st.tabs([
    "💬 Teamroom", 
    "📊 Otto (History & Macro)", 
    "⚡ Signals Journal (Nino)"
])

# ==========================================
# TAB 1: DER TEAMROOM (Zusammenführung & Synthese)
# ==========================================
with tab_teamroom:
    st.subheader("Tägliches Standup & Synthesis")
    st.markdown("Nach Ray Dalios Prinzipien: **Radical Truth & Radical Open-Mindedness**.")
    
    selected_depot = st.selectbox(
        "Fokus-Depot für dieses Meeting:",
        ["Invest (Langfristiges Fundament / Core)", "Swing (Mittelfristige Trendfolge)", "Risiko (Aggressive / Spekulative Plays)"],
        key="teamroom_depot_select"
    )
    
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📊 Ottos aktueller Stand")
        logs = otto.get_logs()
        if logs:
            latest_otto = logs[0]
            st.write(f"**Marktphase:** {latest_otto.get('market_phase', 'N/A')}")
            st.info(latest_otto.get('insight', 'Keine Daten'))
        else:
            st.warning("Otto hat noch kein Standup durchgeführt. Wechsle in den Tab 'Otto'.")
            
    with col2:
        st.markdown("#### ⚡ Ninos letzte Journal-Aktivität")
        journal_logs = nino.get_signals_history()
        if journal_logs:
            latest_nino = journal_logs[0]
            st.write(f"**Letzter Ticker:** {latest_nino.get('ticker')} ({latest_nino.get('signal_typ')})")
            st.info(f"Status: {latest_nino.get('status')} | Max-Perf (5D): {latest_nino.get('max_performance_5_tage', 0):+.2f}%")
        else:
            st.warning("Das Journal ist noch leer.")
        
    st.divider()
    
    team_conclusion = st.text_area(
        "Finaler Team-Beschluss für das gewählte Depot:",
        placeholder="Z.B.: 'Aufgrund von Ottos Makro-Analyse gewichten wir das Invest-Depot defensiver...'"
    )
    if st.button("💾 Entschluss speichern"):
        if team_conclusion:
            try:
                supabase.table("team_decisions").insert({
                    "depot_focus": selected_depot,
                    "decision_text": team_conclusion
                }).execute()
                st.success("Entschluss erfolgreich verankert!")
            except Exception as e:
                st.error(f"Fehler: {e}")
        else:
            st.warning("Bitte Text eingeben.")

# ==========================================
# TAB 2: OTTO (Nutzt ausschließlich `employees/otto.py`)
# ==========================================
with tab_otto:
    st.subheader(f"📊 {otto.name}")
    st.caption(otto.description)
    
    col_o1, col_o2 = st.columns([2, 1])
    
    with col_o1:
        if st.button("🚀 Otto: Analyse & Tages-Standup starten", key="btn_run_otto"):
            with st.spinner("Otto analysiert..."):
                success, msg = otto.run_analysis()
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(f"Fehler: {msg}")
        
        logs = otto.get_logs()
        if logs:
            st.markdown("### 📚 Ottos Logbuch")
            for log in logs:
                with st.expander(f"Standup vom {log['analysis_date']} – Phase: {log.get('market_phase', 'N/A')}"):
                    st.write(log['insight'])
                    if log.get('user_feedback'):
                        st.info(f"Dein Feedback: {log['user_feedback']}")
        else:
            st.info("Noch keine Berichte im Gedächtnis.")
            
    with col_o2:
        st.markdown("#### 💬 Direkt mit Otto sprechen")
        user_input = st.text_area("Anweisung an Otto:", placeholder="Z.B.: 'Achte stärker auf Rohstoffe.'", key="otto_feedback_input")
        if st.button("Anweisung senden", key="btn_send_otto_fb"):
            if user_input:
                success, msg = otto.save_feedback(user_input)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)
            else:
                st.warning("Bitte Nachricht eingeben.")

# ==========================================
# TAB 3: NINO (Reines Signals Journal)
# ==========================================
with tab_nino:
    st.subheader("⚡ Signals Journal")
    st.markdown("Autonomes Archiv aller Screener-Signale inklusive 5-Tages-Peak- und Schlusskurs-Auswertung.")
    
    st.divider()

    # Das Journal direkt laden und anzeigen
    journal_data = nino.get_signals_history()
    
    if journal_data:
        df_nino = pd.DataFrame(journal_data)
        if "id" in df_nino.columns:
            df_nino = df_nino.drop(columns=["id"])
        st.dataframe(df_nino, use_container_width=True)
    else:
        st.info("Das Signals Journal ist noch leer. Sobald Nino im Hintergrund seine Arbeit verrichtet, erscheinen hier die Daten.")