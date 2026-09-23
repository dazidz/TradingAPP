import os
import google.generativeai as genai
import streamlit as st
from datetime import datetime

class ArisAgent:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Aris"
        self.model_name = "gemini-3.6-flash"  # Passe das Modell bei Bedarf an
        self.description = "Performance & Metrik-Agent"

    def _resolve_api_key(self, passed_key: str = None) -> str:
        """Ultimative Schlüsselsuche: Prüft Parameter, Env, alle denkbaren Secret-Namen."""
        if passed_key:
            return passed_key

        # 1. Bekannte Env-Variablen prüfen
        for env_name in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"]:
            val = os.getenv(env_name)
            if val:
                return val

        # 2. Streamlit Secrets durchkämmen
        try:
            if hasattr(st, "secrets") and st.secrets:
                # Direkte Treffer
                for key_name in [
                    "GEMINI_API_KEY",
                    "gemini_api_key",
                    "GOOGLE_API_KEY",
                    "google_api_key",
                    "GEMINI_KEY",
                ]:
                    if key_name in st.secrets and st.secrets[key_name]:
                        return st.secrets[key_name]

                # Verschachtelte Bereiche prüfen (z.B. [api_keys] gemini = "...")
                for section in st.secrets:
                    if isinstance(st.secrets[section], dict):
                        for sub_key in ["gemini_api_key", "GEMINI_API_KEY", "api_key", "key"]:
                            if sub_key in st.secrets[section] and st.secrets[section][sub_key]:
                                return st.secrets[section][sub_key]
        except Exception:
            pass

        return None

    def run_analysis(self, api_key: str = None):
        try:
            active_key = self._resolve_api_key(api_key)
            if not active_key:
                return False, "Kein Gemini API-Key für Aris gefunden (weder übergeben, noch in Env oder Streamlit Secrets vorhanden)."

            genai.configure(api_key=active_key)
            model = genai.GenerativeModel(self.model_name)
            
            # Hier folgt deine spezifische Agenten-Logik (z.B. Daten aus Supabase holen, Prompt senden etc.)
            prompt = "Führe eine Performance- und Metrik-Analyse durch."
            response = model.generate_content(prompt)
            report_content = response.text

            # Optional: In Supabase speichern
            self.supabase.table("agent_reports").insert({
                "agent_name": self.name,
                "report_content": report_content,
                "status": "unread",
                "created_at": datetime.now().isoformat(),
            }).execute()

            return True, "Aris-Analyse erfolgreich durchgeführt und gespeichert!"

        except Exception as e:
            return False, f"Fehler bei der Aris-Analyse: {e}"