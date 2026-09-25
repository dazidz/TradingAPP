from datetime import datetime
import os
import google.generativeai as genai
import streamlit as st


class ArisAgent:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Aris"
        self.model_name = "gemini-3.6-flash"
        self.description = "Performance Manager"

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

            # 1. Daten aus dem Arbeitsspeicher abrufen
            memory_res = (
                self.supabase.table("aris_arbeitsspeicher").select("*").execute()
            )
            memory_data = memory_res.data if memory_res.data else []

            memory_texts = [str(item) for item in memory_data]
            memory_context = (
                "\n".join(memory_texts)
                if memory_texts
                else "Keine spezifischen Einträge im Arbeitsspeicher."
            )

            # 2. Detaillierter Analyse-Prompt nach Vorgabe
            prompt = f"""
            Du bist Aris, der Performance Manager. 
            Deine Aufgabe ist es, die folgenden Rohdaten aus dem Arbeitsspeicher ('aris_arbeitsspeicher') tiefgehend zu analysieren, datenbasierte Erkenntnisse abzuleiten und diese als klare **Principals** (Prinzipien) zu formulieren.

            ARBEITSSPEICHER-DATEN:
            {memory_context}

            Führe folgende Analysen durch:
            - **ADX & SMI Mustererkennung**: Welche Muster oder Kombinationen zeigen sich?
            - **Haltedauer**: Laufen 5-Tage-End-Trades oder Max-Trades besser?
            - **Signal-Performance**: Welche Signale laufen besser? Gibt es eine optimale Signal + ADX + SMI Kombi?
            - **Top 5 des Tages**: Welche Indikatoren und Merkmale weisen die Top 5 des Tages auf?
            - **Sonstige Muster**: Was funktioniert am besten?
            - **Verbesserungstipps**: Konkrete Handlungsempfehlungen.

            Schreibe die zentralen Erkenntnisse strukturiert als 'Principals' nieder.
            """

            response = model.generate_content(prompt)
            report_content = response.text

            # 3. Bericht / Erkenntnisse in agent_reports speichern (als Principals gekennzeichnet)
            self.supabase.table("agent_reports").insert({
                "agent_name": self.name,
                "report_content": report_content,
                "status": "unread",
                "created_at": datetime.now().isoformat(),
            }).execute()

            # 4. Verarbeitete Einträge aus dem Arbeitsspeicher löschen
            for item in memory_data:
                item_id = item.get("id")
                if item_id:
                    self.supabase.table("aris_arbeitsspeicher").delete().eq(
                        "id", item_id
                    ).execute()

            return (
                True,
                "Aris Performance-Analyse erfolgreich durchgeführt, Principals aktualisiert und Arbeitsspeicher geleert!",
            )

        except Exception as e:
            return False, f"Fehler bei der Aris-Analyse: {e}"

    def render_ui(self, api_key: str = None):
        st.subheader(f"🤖 {self.name} - {self.description}")
        st.write(
            "Analysiert den Arbeitsspeicher, erkennt Muster (ADX, SMI, Haltedauer, Top 5) und generiert strategische Principals."
        )

        if st.button(
            f"Analyse & Principals erstellen ({self.name})",
            key=f"btn_run_{self.name}",
        ):
            with st.spinner(
                f"{self.name} wertet den Arbeitsspeicher aus..."
            ):
                success, msg = self.run_analysis(api_key)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)

        st.markdown("---")
        st.markdown("### 📄 Letzte Aris Principals / Berichte")
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


# --- MODUL-EBENE FUNKTION ---
def render_ui(supabase_client, api_key: str = None):
    agent = ArisAgent(supabase_client)
    agent.render_ui(api_key)