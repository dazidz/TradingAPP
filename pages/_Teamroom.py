import streamlit as st
from supabase import create_client
import importlib
import pkgutil
import employees

st.set_page_config(layout="wide", page_title="VisionDZ - Teamroom", page_icon="🏢")

# Sicherheitsprüfung
if not st.session_state.get("password_correct", False):
    st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
    st.stop()

# Supabase Verbindung
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

st.title("🏢 VisionDZ - Teamroom")
st.markdown("Kommandozentrale – Vollautomatisches KI-Mitarbeiter-Management.")

# Automatische Erkennung aller Mitarbeiter im 'employees'-Ordner
@st.cache_resource
def load_employee_registry():
    registry = {}
    for _, module_name, _ in pkgutil.iter_modules(employees.__path__):
        module = importlib.import_module(f"employees.{module_name}")
        # Suche nach Klassen, die von der Basis-Klasse 'Employee' erben (aber nicht Employee selbst sind)
        for attribute_name in dir(module):
            attribute = getattr(module, attribute_name)
            if isinstance(attribute, type) and attribute != employees.otto.Employee:
                # Prüfen ob es eine Methode run_analysis besitzt
                if hasattr(attribute, "run_analysis"):
                    instance = attribute(supabase)
                    registry[instance.name] = instance
    return registry

employee_registry = load_employee_registry()

# Sidebar Auswahl baut sich komplett dynamisch auf!
st.sidebar.markdown("### 🤖 KI-Mitarbeiter")
selected_name = st.sidebar.selectbox("Mitarbeiter wählen:", list(employee_registry.keys()))

st.divider()

# Den aktuell ausgewählten Mitarbeiter laden
current_employee = employee_registry[selected_name]

st.subheader(f"📊 {current_employee.name}")
st.caption(current_employee.description)

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("#### 📝 Arbeitsbereich & Logbuch")
    
    if st.button(f"🚀 {current_employee.name}: Analyse & Tages-Standup starten"):
        with st.spinner(f"{current_employee.name} arbeitet..."):
            success, msg = current_employee.run_analysis()
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(f"Fehler: {msg}")
    
    logs = current_employee.get_logs()
    if logs:
        st.markdown("### 📚 Logbuch & Historie")
        for log in logs:
            with st.expander(f"Standup vom {log['analysis_date']} – Status: {log.get('market_phase', 'N/A')}"):
                st.write(log['insight'])
                if log.get('user_feedback'):
                    st.info(f"Dein Feedback: {log['user_feedback']}")
    else:
        st.info("Noch keine Berichte im Gedächtnis dieses Mitarbeiters vorhanden.")

with col2:
    st.markdown("#### 💬 Direkt sprechen / Training")
    st.markdown("Gib deinem Mitarbeiter Anweisungen oder Feedback:")
    
    user_input = st.text_area("Nachricht:", placeholder="Z.B.: 'Achte stärker auf Kennzahl X.'", key=f"fb_{selected_name}")
    if st.button("Anweisung senden"):
        if user_input:
            success, msg = current_employee.save_feedback(user_input)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.warning(msg)
        else:
            st.warning("Bitte gib eine Nachricht ein.")