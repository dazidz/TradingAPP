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
        self.model_name = "gemini-3.6-flash"
        self.description = "Portfolio Manager"

    def _fetch_dna_from_supabase(self, depot_focus: str):
        """Lädt die Kern-Prinzipien und die mandatspezifischen Kriterien strikt aus Supabase (ohne Fallback)."""
        res = self.supabase.table("joris_dna").select("mandate, rules_content").execute()
        
        if not res.data:
            raise ValueError("Die Tabelle 'joris_dna' in Supabase ist komplett leer!")

        dna_dict = {row["mandate"]: row["rules_content"] for row in res.data}
        
        if "core" not in dna_dict:
            raise KeyError("Das Mandat 'core' (Kern-Prinzipien) fehlt in der Supabase-Tabelle 'joris_dna'!")
            
        if depot_focus not in dna_dict:
            raise KeyError(f"Das angeforderte Mandat '{depot_focus}' wurde nicht in der Supabase-Tabelle 'joris_dna' gefunden!")

        return dna_dict["core"], dna_dict[depot_focus]

    def _get_table_name(self, depot_focus: str) -> str:
        mapping = {
            "invest": "invest_depot",
            "swing": "swing_depot",
            "high_risk": "risk_depot",
        }
        return mapping.get(depot_focus, "invest_depot")

    def _resolve_api_key(self, passed_key=None) -> str:
        if callable(passed_key):
            try:
                passed_key = passed_key()
            except Exception:
                passed_key = None

        if passed_key and isinstance(passed_key, str) and passed_key.strip():
            return passed_key.strip()

        for env_name in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"]:
            val = os.getenv(env_name)
            if val and isinstance(val, str) and val.strip():
                return val.strip()

        try:
            if hasattr(st, "secrets") and st.secrets:
                for key_name in ["GEMINI_API_KEY", "gemini_api_key", "GOOGLE_API_KEY", "google_api_key", "GEMINI_KEY"]:
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
                return False, "Kein Gemini API-Key für Joris gefunden!"

            genai.configure(api_key=active_key)
            model = genai.GenerativeModel(self.model_name)

            # 1. DNA strikt aus Supabase laden (wirft Fehler, wenn Daten fehlen)
            core_principles, active_mandate_criteria = self._fetch_dna_from_supabase(depot_focus)

            # 2. Ungelesene Team-Berichte abrufen
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

            # 3. Daten laden (Depot, Screener, Favoriten)
            table_name = self._get_table_name(depot_focus)
            depot_res = self.supabase.table(table_name).select("*").execute()
            depot_data_text = str(depot_res.data) if depot_res.data else "Keine Einträge."

            screener_res = self.supabase.table("signals").select("*").limit(20).execute()
            screener_data_text = str(screener_res.data) if screener_res.data else "Keine Signale."

            favorites_res = self.supabase.table("favorites").select("*").execute()
            favorites_data_text = str(favorites_res.data) if favorites_res.data else "Keine Favoriten."

            # Irma Sektor-Quoten laden (nur bei swing und high_risk)
            irma_sectors_text = ""
            if depot_focus.lower() in ["swing", "high_risk"]:
                try:
                    wl_res = self.supabase.table("watchlist").select("ticker, sector").execute()
                    wl_data = wl_res.data if wl_res.data else []
                    sector_stats = {}
                    for item in wl_data:
                        sec = item.get("sector") or "Unbekannt"
                        tick = item.get("ticker")
                        if not tick:
                            continue
                        if sec not in sector_stats:
                            sector_stats[sec] = set()
                        sector_stats[sec].add(tick)

                    sig_res = self.supabase.table("signals").select("ticker").execute()
                    sig_data = sig_res.data if sig_res.data else []
                    active_signals = {item.get("ticker") for item in sig_data if item.get("ticker")}

                    rows = []
                    for sec, tickers in sector_stats.items():
                        total = len(tickers)
                        if total == 0:
                            continue
                        signaled = len(tickers.intersection(active_signals))
                        quota = (signaled / total) * 100
                        rows.append({
                            "sector": sec,
                            "total_tickers": total,
                            "signal_tickers": signaled,
                            "signal_quota_percent": round(quota, 2)
                        })

                    df_sec = pd.DataFrame(rows)
                    if not df_sec.empty:
                        df_sec = df_sec.sort_values(by="signal_quota_percent", ascending=False).head(10)
                        irma_sectors_text = f"\n            E) IRMA SEKTOR-QUOTEN (Top 10):\n{df_sec.to_string(index=False)}"
                except Exception:
                    pass

            # 4. Prompt mit den reinen Supabase-Kriterien zusammenbauen
            prompt_content = f"""
            {core_principles}
            
            Fokus-Mandat: {depot_focus.upper()} (Zugehörige Depot-Tabelle: {table_name})
            
            FESTE AUSWAHL- UND PRÜFKRITERIEN AUS DER DATENBANK:
            {active_mandate_criteria}
            
            WICHTIG - TRADINGVIEW LINKS:
            Füge bei **jeder** erwähnten Aktie im Markdown-Format exakt diesen Link ein: `[Ticker](https://www.tradingview.com/chart/?symbol=GETTEX:TICKER)`.

            DATENGRUNDLAGE:
            A) DEPOT ({table_name}): {depot_data_text}
            B) SCREENER (Signale): {screener_data_text}
            C) FAVORITEN: {favorites_data_text}
            D) TEAM-BULLET-POINTS: {reports_text}{irma_sectors_text}
            
            AUFGABE:
            Erstelle eine kompromisslose, datenbasierte Portfolio-Synthese, die sich buchstabengetreu an deine Prinzipien und die obigen Mandatskriterien hält.
            1. Makroökonomische Synthese der Team-Berichte im Sinne von Ray Dalio.
            2. Harte Depot-Prüfung: Entsprechen die aktuellen Positionen streng den Kriterien von '{depot_focus.upper()}'? (Wenn nicht -> Verkaufsempfehlung begründen).
            3. Konkrete Handlungsanweisungen und Top-Empfehlungen auf Basis der Daten.
            
            ZUSATZ-FORMAT FÜR DAS JOURNAL (NUR BEI SWING):
            ===JOURNAL_DATA_START===
            [
              {{"ticker": "AAPL", "setup_reason": "Ausbruch", "target": 220.0, "stop_loss": 175.0}}
            ]
            ===JOURNAL_DATA_END===
            """

            response = model.generate_content(prompt_content)
            report_content = response.text

            # 5. Bericht speichern
            self.supabase.table("agent_reports").insert({
                "agent_name": f"Joris_{depot_focus}",
                "report_content": report_content,
                "bullet_points": [
                    f"Synthese Mandat {depot_focus.upper()} strikt nach Supabase-DNA durchgeführt",
                    "Frische Team-Daten und Screener-Signale analysiert",
                ],
                "status": "unread",
                "created_at": datetime.now().isoformat(),
            }).execute()

            # 6. Team-Berichte auf 'processed' setzen
            for rep_id in processed_report_ids:
                self.supabase.table("agent_reports").update({"status": "processed"}).eq(
                    "id", rep_id
                ).execute()

            # 7. Journal befüllen bei Swing
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

    def render_ui(self, api_key=None):
        st.subheader(f"🤖 {self.name} - {self.description}")
        st.write("Führt portfolioübergreifende Synthesen nach rein in Supabase gepflegter DNA aus.")

        depot_focus = st.selectbox(
            "Fokus-Mandat wählen:", ["invest", "swing", "high_risk"], key=f"sel_depot_{self.name}"
        )

        # Versuche die DNA zu laden – wenn etwas in Supabase fehlt, wird es direkt in der UI angezeigt
        try:
            core, active_rules = self._fetch_dna_from_supabase(depot_focus)
            dna_loaded_successfully = True
        except Exception as e:
            dna_loaded_successfully = False
            error_message = str(e)

        with st.expander(f"🧬 Joris' aktive Supabase-DNA für '{depot_focus.upper()}'"):
            if dna_loaded_successfully:
                st.markdown("**Core Principles (aus DB):**")
                st.code(core, language="text")
                st.markdown(f"**Mandats-Kriterien ({depot_focus.upper()} aus DB):**")
                st.code(active_rules, language="text")
            else:
                st.error(f"Fehler beim Laden der DNA aus Supabase: {error_message}")
                st.warning(f"Bitte stelle sicher, dass die Tabelle `joris_dna` existiert und die Einträge für 'core' sowie das gewählte Mandat ('{depot_focus}') vorhanden sind.")

        if dna_loaded_successfully:
            if st.button(f"Portfolio-Synthese starten ({self.name})", key=f"btn_run_{self.name}"):
                with st.spinner(f"{self.name} lädt DNA aus Supabase und analysiert..."):
                    success, msg = self.run_synthesis(depot_focus, api_key)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
        else:
            st.button(f"Portfolio-Synthese starten ({self.name})", key=f"btn_run_{self.name}", disabled=True)

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