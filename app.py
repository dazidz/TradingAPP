import streamlit as st

st.set_page_config(page_title="Test", page_icon="🧪")

st.title("🧪 Minimaler Test")
st.success("Wenn du das siehst, läuft Streamlit Cloud und das Grundsystem lebt!")

# Teste Secrets
try:
    pw = st.secrets["APP_PASSWORD"]
    st.write("✅ Sekret 'APP_PASSWORD' wurde erfolgreich gelesen.")
except Exception as e:
    st.error(f"❌ Fehler beim Lesen der Secrets: {e}")