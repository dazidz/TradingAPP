from datetime import datetime
import json
import os
import re
import google.generativeai as genai
import pandas as pd
import streamlit as st

AGENT_TITLE = "Joris"

class JorisPortfolioManager:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Joris"
        self.model_name = "gemini-2.5-flash"  # Oder dein gewünschtes Modell
        self.description = "Portfolio Manager & Synthese-Agent nach Ray Dalios Prinzipien."

    def _get_table_name(self, depot_focus: str) -> str:
        mapping = {
            "invest": "invest_depot",
            "swing": "swing_depot",
            "high_risk": "risk_depot",
        }
        return mapping.get(depot_focus, "invest_depot")

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

    def run_synthesis(self, depot_focus: str, api_key=None):
        try:
            active_key = self._resolve_api_key(api_key)
            if not active_key:
                return False, "Kein Gemini API-Key für Joris gefunden! Bitte prüfe deine Secrets."

            genai.configure(api_key=active_key)
            model = genai.GenerativeModel(self.model_name)

            # 1. NUR UNGELESENE BERICHTE DER KOLLEGEN ABRUFEN (Status = 'unread')
            reports_res = (
                self.supabase.table("agent_reports")
                .select("id, created_at, agent_name, bullet_points, report_content")
                .eq("status", "unread")
                .order("created_at", desc=True)
                .execute()
            )

            raw_reports = reports_res.data if reports_res.data else []

            formatted_reports_list = []
            processed_report_ids = []

            for rep in raw_reports:
                agent = rep.get("agent_name", "Unbekannt")
                if "Joris" in agent:
                    continue

                processed_report_ids.append(rep.get("id"))
                bullets = rep.get("bullet_points")

                if bullets:
                    formatted_reports_list.append(
                        f"--- Agent: {agent} (vom {rep.get('created_at')}) ---\n"
                        + "\n".join([f"- {b}" for b in bullets])
                    )
                else:
                    content = rep.get("report_content", "")
                    formatted_reports_list.append(
                        f"--- Agent: {agent} ---\n{content[:300]}"
                    )

            reports_text = (
                "\n\n".join(formatted_reports_list)
                if formatted_reports_list
                else "Keine neuen Team-Bullet-Points vorhanden."
            )

            # 2. Depot, Signale und Favoriten laden
            table_name = self._get_table_name(depot_focus)
            depot_res = self.supabase.table(table_name).select("*").execute()
            depot_data_text = str(depot_res.data) if depot_res.data else "Keine Einträge."

            screener_res = (
                self.supabase.table("signals").select("*").limit(20).execute()
            )
            screener_data_text = str(screener_res.data) if screener_res.data else "Keine Signale."

            favorites_res = self.supabase.table("favorites").select("*").execute()
            favorites_data_text = str(favorites_res.data) if favorites_res.data else "Keine Favoriten."

            # Prompt zusammenbauen
            prompt_content = f"""
            Du bist Joris, der leitende Portfolio Manager. 
            Deine Arbeitsweise folgt Ray Dalios Prinzipien: **Radical Truth & Radical Open-Mindedness**.
            Fokus-Mandat: {depot_focus.upper()} (Zugehörige Depot-Tabelle: {table_name})
            
            WICHTIG - TRADINGVIEW LINKS:
            Füge bei **jeder** erwähnten Aktie im Markdown-Format einen Link ein: `[Ticker](https://www.tradingview.com/chart/?symbol=NASDAQ:TICKER)`.

            DATENGRUNDLAGE (Nur frische Team-Bullet-Points):
            A) DEPOT ({table_name}): {depot_data_text}
            B) SCREENER: {screener_data_text}
            C) FAVORITEN: {favorites_data_text}
            D) NEUESTE TEAM-BULLET-POINTS: {reports_text}
            
            AUFGABE:
            Erstelle eine datenbasierte Portfolio-Synthese für '{depot_focus.upper()}'. 
            1. Zusammenfassung & Synthese der Bullet-Points.
            2. Depot-Prüfung & Diversifikation.
            3. Verkaufsempfehlungen.
            4. Top-Empfehlungen des Tages.
            
            ZUSATZ-FORMAT FÜR DAS JOURNAL (BEI SWING):
            ===JOURNAL_DATA_START===
            [
              {{"ticker": "AAPL", "setup_reason": "Ausbruch", "target": 220.0, "stop_loss": 175.0}}
            ]
            ===JOURNAL_DATA_END===
            """

            response = model.generate_content(prompt_content)
            report_content = response.text

            # 3. Bericht in agent_reports speichern
            self.supabase.table("agent_reports").insert({
                "agent_name": f"Joris_{depot_focus}",
                "report_content": report_content,
                "bullet_points": [
                    f"Synthese Mandat {depot_focus.upper()} erfolgreich abgeschlossen",
                    "Frische Team-Daten und Screener-Signale verarbeitet",
                ],
                "status": "unread",
                "created_at": datetime.now().isoformat(),
            }).execute()

            # 4. Verarbeitete Team-Berichte auf 'processed' setzen
            for rep_id in processed_report_ids:
                self.supabase.table("agent_reports").update({"status": "processed"}).eq(
                    "id", rep_id
                ).execute()

            # 5. Journal befüllen bei Swing
            if depot_focus.lower() == "swing":
                match = re.search(
                    r"===JOURNAL_DATA_START===\s*(.*?)\s*===JOURNAL_DATA_END===",
                    report_content,
                    re.DOTALL,
                )
                if match:
                    picks = json.loads(match.group(1))
                    for pick in picks:
                        self.supabase.table("joris_journal").insert({
                            "ticker": pick.get("ticker", "UNKNOWN"),
                            "setup_reason": pick.get("setup_reason", ""),
                            "target": float(pick.get("target", 0.0)),
                            "stop_loss": float(pick.get("stop_loss", 0.0)),
                            "status": "active",
                            "created_at": datetime.now().isoformat(),
                        }).execute()

            return True, f"Synthese für '{table_name}' erfolgreich erstellt!"
        except Exception as e:
            return False, f"Fehler bei der Synthese: {e}"

    def get_latest_report(self, depot_focus: str):
        try:
            agent_name = f"Joris_{depot_focus}"
            res = (
                self.supabase.table("agent_reports")
                .select("*")
                .eq("agent_name", agent_name)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            return None

    def chat_with_joris(
        self,
        depot_focus: str,
        user_message: str,
        chat_history: list,
        api_key=None,
    ):
        try:
            active_key = self._resolve_api_key(api_key)
            if not active_key:
                return False, "Kein Gemini API-Key für den Joris-Chat gefunden."

            genai.configure(api_key=active_key)
            model = genai.GenerativeModel(self.model_name)

            formatted_history = []
            for msg in chat_history:
                role = "user" if msg["role"] == "user" else "model"
                formatted_history.append({"role": role, "parts": [msg["content"]]})

            chat = model.start_chat(history=formatted_history)

            system_context = f"""
            Du bist Joris, der leitende Portfolio Manager. Du chattest mit deinem Vorgesetzten.
            Aktuelles Fokus-Mandat: {depot_focus.upper()}.
            Handle stets nach Ray Dalios Prinzipien: Radical Truth & Radical Open-Mindedness.
            Antworte präzise, analytisch und direkt auf Basis der vorliegenden Mandatsdaten.
            """

            full_prompt = f"{system_context}\n\nFrage des Nutzers: {user_message}"
            response = chat.send_message(full_prompt)
            return True, response.text
        except Exception as e:
            return False, f"Fehler im Chat mit Joris: {e}"

    def render_ui(self, api_key=None):
        st.subheader(f"🤖 {self.name} - {self.description}")
        st.write("Führt portfolioübergreifende Synthesen nach Ray Dalios Prinzipien durch.")

        depot_focus = st.selectbox(
            "Fokus-Mandat wählen:", ["invest", "swing", "high_risk"], key=f"sel_depot_{self.name}"
        )

        if st.button(f"Portfolio-Synthese starten ({self.name})", key=f"btn_run_{self.name}"):
            with st.spinner(f"{self.name} analysiert Berichte und Depots..."):
                success, msg = self.run_synthesis(depot_focus, api_key)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)

        st.markdown("---")
        st.markdown(f"### 📄 Letzter Synthese-Bericht ({depot_focus.upper()})")
        report = self.get_latest_report(depot_focus)
        if report:
            st.caption(f"Erstellt am: {report.get('created_at', 'Unbekannt')}")
            st.markdown(report.get("report_content", "Kein Inhalt."))
        else:
            st.info("Noch kein Synthese-Bericht für dieses Mandat vorhanden.")


# --- MODUL-EBENE FUNKTION ---
def render_ui(supabase_client, api_key=None):
    agent = JorisPortfolioManager(supabase_client)
    agent.render_ui(api_key)