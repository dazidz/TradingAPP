from datetime import datetime
import os
import google.generativeai as genai
import streamlit as st


class ArisAgent:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Aris"
        self.model_name = "gemini-1.5-flash"
        self.description = "Performance & Metrik-Agent"

    def _resolve_api_key(self, passed_key: str = None) -> str:
        """Ultimative Schlüsselsuche: Prüft Parameter, Env, alle denkbaren Secret-Namen."""
        if passed_key:
            return passed_key

        for env_name in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"]:
            val = os.getenv(env_name)
            if val:
                return val

        try:
            if hasattr(st, "secrets") and st.secrets:
                for key_name in [
                    "GEMINI_API_KEY",
                    "gemini_api_key",
                    "GOOGLE_API_KEY",
                    "google_api_key",
                    "GEMINI_KEY",
                ]:
                    if key_name in st.secrets and st.secrets[key_name]:
                        return st.secrets[key_name]

                for section in st.secrets:
                    if isinstance(st.secrets[section], dict):
                        for sub_key in [
                            "gemini_api_key",
                            "GEMINI_API_KEY",
                            "api_key",
                            "key",
                        ]:
                            if (
                                sub_key in st.secrets[section]
                                and st.secrets[section][sub_key]
                            ):
                                return st.secrets[section][sub_key]
        except Exception:
            pass

        return None

    def run_analysis(self, api_key: str = None):
        try:
            active_key = self._resolve_api_key(api_key)
            if not active_key:
                return False, "Kein Gemini API-Key für Aris gefunden."

            genai.configure(api_key=active_key)
            model = genai.GenerativeModel(self.model_name)

            prompt = (
                "Führe eine Performance- und Metrik-Analyse für das Portfolio durch."
            )
            response = model.generate_content(prompt)
            report_content = response.text

            self.supabase.table("agent_reports").insert({
                "agent_name": self.name,
                "report_content": report_content,
                "status": "unread",
                "created_at": datetime.now().isoformat(),
            }).execute()

            return (
                True,
                "Aris-Analyse erfolgreich durchgeführt und gespeichert!",
            )

        except Exception as e:
            return False, f"Fehler bei der Aris-Analyse: {e}"

    def render_ui(self, api_key: str = None):
        st.subheader(f"🤖 {self.name} - {self.description}")
        st.write(
            "Verantwortlich für Performance-Auswertungen, Metriken und statistische Validierung."
        )

        if st.button(
            f"Analyse starten ({self.name})", key=f"btn_run_{self.name}"
        ):
            with st.spinner(f"{self.name} analysiert die Daten..."):
                success, msg = self.run_analysis(api_key)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)

        st.markdown("---")
        st.markdown("### 📄 Letzter Aris-Bericht")
        try:
            res = (
                self.supabase.table("agent_reports")
                .select("*")
                .eq("agent_name", self.name)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if res.data:
                report = res.data[0]
                st.caption(
                    f"Erstellt am: {report.get('created_at', 'Unbekannt')}"
                )
                st.markdown(report.get("report_content", "Kein Inhalt."))
            else:
                st.info("Noch kein Bericht von Aris vorhanden.")
        except Exception as e:
            st.warning(f"Fehler beim Laden des Berichts aus Supabase: {e}")


# --- MODUL-EBENE FUNKTION (Falls das Testskript direkt das Modul prüft) ---
def render_ui(supabase_client, api_key: str = None):
    agent = ArisAgent(supabase_client)
    agent.render_ui(api_key)