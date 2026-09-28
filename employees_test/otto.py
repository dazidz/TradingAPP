from datetime import datetime
import os
import google.generativeai as genai
import pandas as pd
import streamlit as st
import yfinance as yf

AGENT_TITLE = "Otto"

class OttoAnalyst:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Otto"
        self.model_name = "gemini-2.5-flash"  # Auf stabiles Standard-Modell angepasst
        self.description = (
            "History & Patterns Analyst (Muster-Matching, historische Korrelationen, analoge Börsenphasen)"
        )

        self.otto_dna = """
        Du bist Otto, der leitende Historien- und Muster-Analyst in unserem Team. Deine Brille ist strikt quantitativ-historisch.
        Du vergleichst aktuelle Marktphasen, Volatilitäten und Zinsumfelder mit historischen Krisen, Blasen und Boom-Phasen (z.B. 2000, 2008, 2020, 2022).
        
        Deine Aufgabe:
        1. Analysiere historische Muster anhand von Kurs- und Volatilitätsdaten.
        2. Zeige Parallelen und Unterschiede zu früheren Börsenzyklen auf.
        3. Warne vor historischen Fallen oder bestätige historische Chancen faktenbasiert.
        """

    def _resolve_api_key(self, passed_key=None) -> str:
        """Ermittelt den API-Key extrem robust (unterstützt Callables, Env und Streamlit Secrets)."""
        if callable(passed_key):
            try:
                passed_key = passed_key()
            except Exception:
                passed_key = None

        if passed_key and isinstance(passed_key, str) and passed_key.strip():
            return passed_key.strip()

        # 1. Bekannte Env-Variablen prüfen
        for env_name in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"]:
            val = os.getenv(env_name)
            if val and isinstance(val, str) and val.strip():
                return val.strip()

        # 2. Streamlit Secrets durchkämmen
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
                        return str(st.secrets[key_name]).strip()

                for section in st.secrets:
                    try:
                        sec_content = st.secrets[section]
                        if isinstance(sec_content, dict):
                            for sub_key in ["gemini_api_key", "GEMINI_API_KEY", "google_api_key", "GOOGLE_API_KEY", "api_key", "key"]:
                                if sub_key in sec_content and sec_content[sub_key]:
                                    return str(sec_content[sub_key]).strip()
                    except Exception:
                        continue
        except Exception:
            pass

        return ""

    def fetch_historical_context(self):
        """Holt historische S&P 500 Daten für das Muster-Matching."""
        try:
            t = yf.Ticker("^GSPC")
            hist = t.history(period="5y")
            if hist.empty:
                return "Keine historischen Daten verfügbar."

            recent_close = hist["Close"].iloc[-1]
            high_1y = hist["Close"].tail(252).max()
            low_1y = hist["Close"].tail(252).min()

            return (
                f"S&P 500 aktueller Stand: {recent_close:.2f}\n"
                f"1-Jahres-Hoch: {high_1y:.2f}\n"
                f"1-Jahres-Tief: {low_1y:.2f}"
            )
        except Exception as e:
            return f"Fehler beim Laden historischer Daten: {e}"

    def run_analysis(self, api_key=None):
        """Führt Ottos historische Muster-Analyse aus und speichert sie in agent_reports."""
        try:
            active_key = self._resolve_api_key(api_key)
            if not active_key:
                return False, "Kein Gemini API-Key für Otto gefunden! Bitte prüfe deine Secrets."

            genai.configure(api_key=active_key)

            history_context = self.fetch_historical_context()

            context = f"""
            --- HISTORISCHER KONTEXT & MARKT-MUSTER ---
            {history_context}
            """

            model = genai.GenerativeModel(
                model_name=self.model_name, system_instruction=self.otto_dna
            )
            response = model.generate_content(
                "Führe ein historisches Muster-Matching und einen "
                f"Zyklus-Vergleich durch:\n\n{context}"
            )

            report_content = response.text
            today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

            # Zentral in agent_reports speichern
            self.supabase.table("agent_reports").insert({
                "agent_name": self.name,
                "report_content": f"**Report vom {today_str}:**\n\n{report_content}",
            }).execute()

            return (
                True,
                "Otto hat die historische Muster-Analyse erfolgreich abgeschlossen.",
            )
        except Exception as e:
            return False, f"Fehler bei Ottos Analyse: {e}"

    def get_latest_report(self):
        """Holt den neuesten Bericht von Otto aus der zentralen Tabelle."""
        try:
            res = (
                self.supabase.table("agent_reports")
                .select("*")
                .eq("agent_name", self.name)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            return None

    def render_ui(self, api_key=None):
        st.subheader(f"🤖 {self.name} - {self.description}")
        st.write("Vergleicht aktuelle Märkte mit historischen Zyklen, Krisen und Mustern.")

        if st.button(f"Historische Analyse starten ({self.name})", key=f"btn_run_{self.name}"):
            with st.spinner(f"{self.name} durchsucht historische Muster..."):
                success, msg = self.run_analysis(api_key)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)

        st.markdown("---")
        st.markdown(f"### 📄 Letzter Bericht von {self.name}")
        report = self.get_latest_report()
        if report:
            st.caption(f"Erstellt am: {report.get('created_at', 'Unbekannt')}")
            st.markdown(report.get("report_content", "Kein Inhalt."))
        else:
            st.info("Noch kein Bericht von Otto vorhanden.")


# --- MODUL-EBENE FUNKTION ---
def render_ui(supabase_client, api_key=None):
    agent = OttoAnalyst(supabase_client)
    agent.render_ui(api_key)