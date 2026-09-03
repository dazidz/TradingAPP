import streamlit as st
from supabase import create_client

# Importiere die sauberen, separaten Mitarbeiter-Klassen
from employees.otto import OttoAnalyst
# Später einfach: from employees.risk_manager import RiskManager

st.set_page_config(layout="wide", page_title="VisionDZ - Team & Kommandozentrale", page_icon="🏢")

if not st.session_state.get("password_correct", False):
    st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
    st.stop()

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# Mitarbeiter-Instanzen erzeugen
otto = OttoAnalyst(supabase)
# risk_manager = RiskManager(supabase)

st.title("🏢 VisionDZ - Team & Kommandozentrale")

# --- DIE TABS DEFINIEREN ---
tab_teamroom, tab_otto, tab_risk = st.tabs(["💬 Teamroom", "📊 Otto (History & Macro)", "🛡️ Risk Manager"])

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
        # Holt Ottos Berichte direkt über seine eigenen Methoden/Daten
        logs = otto.get_logs()
        if logs:
            latest_otto = logs[0]
            st.write(f"**Marktphase:** {latest_otto.get('market_phase', 'N/A')}")
            st.info(latest_otto.get('insight', 'Keine Daten'))
        else:
            st.warning("Otto hat noch kein Standup durchgeführt. Wechsle in den Tab 'Otto'.")
            
    with col2:
        st.markdown("#### 🛡️ Risk Manager")
        st.info("Wartet auf Integration des separaten `risk_manager.py`-Codes...")
        
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
# TAB 3: RISK MANAGER (Platzhalter für den nächsten Mitarbeiter-Code)
# ==========================================
with tab_risk:
    st.subheader("🛡️ Risk Management & Quant")
    st.markdown("Sobald du `employees/risk_manager.py` anlegst, binden wir ihn hier analog zu Otto ein.")