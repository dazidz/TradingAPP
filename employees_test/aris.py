from datetime import datetime
import os
import requests
import streamlit as st


class ArisAgent:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Aris"
        self.model_name = "openai/gpt-oss-120b"
        self.description = "Performance Manager"

    def _resolve_api_key(self, passed_key: str = None) -> str:
        if passed_key and isinstance(passed_key, str) and passed_key.strip():
            return passed_key.strip()

        # 1. Prüfe Umgebungsvariablen (inklusive GROQ_API_KEY)
        for env_name in ["GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "OPENAI_KEY"]:
            val = os.getenv(env_name)
            if val and isinstance(val, str) and val.strip():
                return val.strip()

        # 2. Prüfe Streamlit Secrets (inklusive GROQ_API_KEY)
        try:
            if hasattr(st, "secrets") and st.secrets:
                for key_name in ["GROQ_API_KEY", "groq_api_key", "OPENROUTER_API_KEY", "openrouter_api_key", "OPENAI_API_KEY", "openai_api_key"]:
                    if key_name in st.secrets:
                        val = st.secrets[key_name]
                        if val and isinstance(val, str):
                            return val.strip()
                
                for section in st.secrets:
                    if isinstance(st.secrets[section], dict):
                        for sub_key in ["groq_api_key", "GROQ_API_KEY", "openrouter_api_key", "OPENROUTER_API_KEY", "openai_api_key", "OPENAI_API_KEY", "api_key", "key"]:
                            if sub_key in st.secrets[section]:
                                val = st.secrets[section][sub_key]
                                if val and isinstance(val, str):
                                    return val.strip()
        except Exception:
            pass
            
        return ""

    def run_analysis(self, api_key: str = None):
        try:
            active_key = self._resolve_api_key(api_key)
            if not active_key:
                return False, "Kein API-Key gefunden! Bitte hinterlege deinen GROQ_API_KEY in den Streamlit Secrets."

            # 1. Daten aus dem Arbeitsspeicher abrufen
            memory_res = (
                self.supabase.table("aris_arbeitsspeicher").select("*").execute()
            )
            memory_data = memory_res.data if memory_res.data else []

            if not memory_data:
                return False, "Keine Einträge im Arbeitsspeicher vorhanden."

            # Kompakte Formatierung der Einträge
            context_lines = [
                f"- Ticker: {item.get('ticker')}, Typ: {item.get('signal_typ')}, SMI: {item.get('smi')}, ADX: {item.get('adx')}, EMA20: {item.get('above_ema20')}, Perf 5T: {item.get('end_performance_5_tage')}%"
                for item in memory_data
            ]
            memory_context = "\n".join(context_lines)

            # 2. Prompt aufbauen
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

            # 3. API-Aufruf (Standardmäßig OpenRouter; falls es direkt über Groq läuft, kann hier die URL angepasst werden)
            headers = {
                "Authorization": f"Bearer {active_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://streamlit.io",
                "X-Title": "Trading App Aris"
            }

            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": "Du bist Aris, ein präziser Performance Manager für Trading-Strategien."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3
            }

            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120.0
            )

            if response.status_code != 200:
                return False, f"API-Fehler ({response.status_code}): {response.text}"

            res_json = response.json()
            report_content = res_json["choices"][0]["message"]["content"]

            # 4. Bericht in agent_reports speichern
            self.supabase.table("agent_reports").insert({
                "agent_name": self.name,
                "report_content": report_content,
                "status": "unread",
                "created_at": datetime.now().isoformat(),
            }).execute()

            # 5. Arbeitsspeicher leeren
            for item in memory_data:
                item_id = item.get("id")
                if item_id:
                    self.supabase.table("aris_arbeitsspeicher").delete().eq("id", item_id).execute()

            return True, "Aris Performance-Analyse erfolgreich mit gpt-oss-120b durchgeführt!"

        except Exception as e:
            return False, f"Fehler bei der Aris-Analyse: {e}"

    def render_ui(self, api_key: str = None):
        st.subheader(f"🤖 {self.name} - {self.description}")
        st.write("Analysiert den Arbeitsspeicher über gpt-oss-120b, erkennt Muster und generiert strategische Principals.")

        if st.button(f"Analyse & Principals erstellen ({self.name})", key=f"btn_run_{self.name}"):
            with st.spinner(f"{self.name} wertet den Arbeitsspeicher aus..."):
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
                st.caption(f"Erstellt am: {report.get('created_at', 'Unbekannt')}")
                st.markdown(report.get("report_content", "Kein Inhalt."))
            else:
                st.info("Noch kein Bericht von Aris vorhanden.")
        except Exception as e:
            st.warning(f"Fehler beim Laden des Berichts aus Supabase: {e}")


# --- MODUL-EBENE FUNKTION ---
def render_ui(supabase_client, api_key: str = None):
    agent = ArisAgent(supabase_client)
    agent.render_ui(api_key)