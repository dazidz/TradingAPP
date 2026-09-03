import streamlit as st
from supabase import create_client
from employees import get_all_employees

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
st.markdown("Kommandozentrale – Tägliches Standup mit deinen KI-Mitarbeitern.")

# Mitarbeiter über die Zentrale laden
employees_list = get_all_employees(supabase)
employee_registry = {emp.name: emp for emp in employees_list}

# Sicherheits-Check, falls keine Mitarbeiter gefunden wurden
if not employee_registry:
  st.error(
      "⚠️ Es konnten keine KI-Mitarbeiter im Ordner `employees/` geladen"
      " werden. Bitte prüfe, ob `employees/otto.py` und die `__init__.py`"
      " korrekt hinterlegt sind."
  )
  st.stop()

# Sidebar Auswahl
st.sidebar.markdown("### 🤖 KI-Mitarbeiter")
selected_name = st.sidebar.selectbox(
    "Mitarbeiter wählen:", list(employee_registry.keys())
)

st.divider()

# Den aktuell ausgewählten Mitarbeiter sicher laden
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
      with st.expander(
          f"Standup vom {log['analysis_date']} – Status:"
          f" {log.get('market_phase', 'N/A')}"
      ):
        st.write(log['insight'])
        if log.get('user_feedback'):
          st.info(f"Dein Feedback: {log['user_feedback']}")
  else:
    st.info("Noch keine Berichte im Gedächtnis dieses Mitarbeiters vorhanden.")

with col2:
  st.markdown("#### 💬 Direkt sprechen / Training")
  st.markdown("Gib deinem Mitarbeiter Anweisungen oder Feedback:")

  user_input = st.text_area(
      "Nachricht:",
      placeholder="Z.B.: 'Achte stärker auf Kennzahl X.'",
      key=f"fb_{selected_name}",
  )
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