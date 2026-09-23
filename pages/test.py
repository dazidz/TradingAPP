import streamlit as st
import importlib
import pkgutil
from supabase import create_client
import os

st.set_page_config(layout="wide", page_title="VisionDZ - Test Umgebung", page_icon="🧪")

st.info("🧪 **Test-Modus aktiv:** Hier wird das neue Plugin-System erprobt.")

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

def get_gemini_api_key():
    if "GEMINI_API_KEY" in globals() and globals()["GEMINI_API_KEY"]:
        return globals()["GEMINI_API_KEY"]
    try:
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            if st.secrets["GEMINI_API_KEY"]:
                return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY")

st.title("🧪 Team - Test-Zentrale")

# Lädt dynamisch den neuen Test-Ordner
import employees_test

agent_modules = {}
for _, module_name, _ in pkgutil.iter_modules(employees_test.__path__):
    mod = importlib.import_module(f"employees_test.{module_name}")
    agent_name = getattr(mod, "AGENT_TITLE", module_name.capitalize())
    agent_modules[agent_name] = mod

if not agent_modules:
    st.warning("Keine Mitarbeiter im `employees_test/`-Ordner gefunden.")
else:
    agent_names = list(agent_modules.keys())
    tabs = st.tabs([f"🤖 {name}" for name in agent_names])

    for i, name in enumerate(agent_names):
        with tabs[i]:
            mod = agent_modules[name]
            if hasattr(mod, "render_ui"):
               actual_key = get_gemini_api_key()
               mod.render_ui(supabase, lambda: actual_key)
            else:
                st.error(f"Mitarbeiter '{name}' besitzt keine `render_ui` Funktion.")