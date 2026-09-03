import streamlit as st
from supabase import create_client
from employees.otto import OttoAnalyst

st.set_page_config(layout="wide", page_title="Teamroom - Otto", page_icon="📊")

if not st.session_state.get("password_correct", False):
    st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
    st.stop()

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

otto = OttoAnalyst(supabase)

st.title(f"📊 {otto.name}")
st.caption(f"Teamroom Unterseite • {otto.description}")

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("#### 📝 Arbeitsbereich & Logbuch")
    
    if st.button("🚀 Otto: Analyse & Tages-Standup starten"):
        with st.spinner("Otto analysiert Zyklen und Watchlist..."):
            success, msg = otto.run_analysis()
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(f"Fehler: {msg}")
    
    logs = otto.get_logs()
    if logs:
        st.markdown("### 📚 Logbuch & Historie")
        for log in logs:
            with st.expander(f"Standup vom {log['analysis_date']} – Phase: {log.get('market_phase', 'N/A')}"):
                st.write(log['insight'])
                if log.get('user_feedback'):
                    st.info(f"Dein Feedback: {log['user_feedback']}")
    else:
        st.info("Noch keine Berichte im Gedächtnis.")

with col2:
    st.markdown("#### 💬 Direkt mit Otto sprechen")
    user_input = st.text_area("Anweisung an Otto:", placeholder="Z.B.: 'Achte stärker auf Rohstoffe.'")
    if st.button("Anweisung senden"):
        if user_input:
            success, msg = otto.save_feedback(user_input)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.warning(msg)
        else:
            st.warning("Bitte gib eine Nachricht ein.")