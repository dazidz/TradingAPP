from datetime import datetime
import os
import google.generativeai as genai
import pandas as pd
import streamlit as st
import yfinance as yf

AGENT_TITLE = "Jano"

class JanoMacroAnalyst:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Jano"
        self.description = "Makro-Analyst (Zyklen, Zinsen, VIX, Rohstoffe, Top-Down)"
        self.model_name = "gemini-3.6-flash" # Auf Standard-Modell angepasst (oder dein bevorzugtes Gemini-Modell)

        self.jano_dna = """
        Du bist Jano, der leitende Makro-Analyst in unserem Team. Deine Brille ist strikt Top-Down.
        Du analysierst Zyklen, Zinsen, den VIX, Rohstoffe, globale Liquidität und die übergeordnete Marktphase (Bullenmarkt, Bärenmarkt, Seitwärtsphase/Korrektur).
        
        Deine Aufgabe:
        1. Bewerte die aktuelle makroökonomische Großwetterlage anhand der gelieferten Kennzahlen.
        2. Leite daraus ab, welches Marktumfeld wir aktuell haben und ob Risiko-Assets (wie Aktien) Rückenwind oder Gegenwind haben.
        3. Fasse deine Erkenntnisse prägnant, analytisch und ungeschönt zusammen.
        """

    def _resolve_api_key(self, passed_key=None) -> str:
        """Ermittelt den API-Key robust (unterstützt auch Callables/Lambdas)."""
        if callable(passed_key):
            try:
                passed_key = passed_key()
            except Exception:
                passed_key = None

        if passed_key and isinstance(passed_key, str) and passed_key.strip():
            return passed_key.strip()

        # Umgebungsvariablen prüfen
        for env_name in ["GEMINI_API_KEY", "GOOGLE_API_KEY"]:
            val = os.getenv(env_name)
            if val and isinstance(val, str) and val.strip():
                return val.strip()

        # Streamlit Secrets prüfen
        try:
            if hasattr(st, "secrets"):
                if "GEMINI_API_KEY" in st.secrets:
                    k = str(st.secrets["GEMINI_API_KEY"]).strip()
                    if k:
                        return k
                if "GOOGLE_API_KEY" in st.secrets:
                    k = str(st.secrets["GOOGLE_API_KEY"]).strip()
                    if k:
                        return k
                
                for section in st.secrets:
                    try:
                        sec_content = st.secrets[section]
                        if isinstance(sec_content, dict):
                            for k_name in ["gemini_api_key", "GEMINI_API_KEY", "google_api_key", "GOOGLE_API_KEY"]:
                                if k_name in sec_content and sec_content[k_name]:
                                    return str(sec_content[k_name]).strip()
                    except Exception:
                        continue
        except Exception:
            pass
            
        return ""

    def fetch_macro_data(self):
        """Holt wichtige Makro-Indikatoren über yfinance."""
        tickers = {
            "S&P 500": "^GSPC",
            "Nasdaq 100": "^NDX",
            "VIX (Volatility)": "^VIX",
            "US 10Y Yield": "^TNX",
            "Gold": "GC=F",
            "Crude Oil": "CL=F",
            "EUR/USD": "EURUSD=X",
        }

        macro_data = {}
        for name, ticker in tickers.items():
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="5d")
                if not hist.empty:
                    current_val = hist["Close"].iloc[-1]
                    prev_val = hist["Close"].iloc[0]
                    change_pct = ((current_val - prev_val) / prev_val) * 100
                    macro_data[name] = {
                        "Aktuell": round(current_val, 2),
                        "5T-Change (%)": round(change_pct, 2),
                    }
            except Exception:
                continue

        return macro_data

    def run_analysis(self, api_key=None):
        """Führt die Makro-Analyse aus und speichert sie zentral in agent_reports."""
        try:
            active_key = self._resolve_api_key(api_key)
            if not active_key:
                return False, "Kein Gemini API-Key gefunden! Bitte prüfe deine Secrets."

            # Gemini konfigurieren
            genai.configure(api_key=active_key)

            macro_metrics = self.fetch_macro_data()
            df_macro = pd.DataFrame(macro_metrics).T

            context = f"""
            --- AKTUELLE MAKRO-DATEN (YFINANCE) ---
            {df_macro.to_string() if not df_macro.empty else "Keine Daten abrufbar"}
            """

            model = genai.GenerativeModel(
                model_name=self.model_name, system_instruction=self.jano_dna
            )
            response = model.generate_content(
                "Analysiere die aktuelle Makro-Lage basierend auf diesen Daten"
                f" und bestimme die Marktphase:\n\n{context}"
            )

            report_content = response.text
            today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

            # Zentral in agent_reports speichern
            self.supabase.table("agent_reports").insert({
                "agent_name": self.name,
                "report_content": f"**Report vom {today_str}:**\n\n{report_content}",
            }).execute()

            return True, "Jano hat die Makro-Analyse erfolgreich abgeschlossen."
        except Exception as e:
            return False, f"Fehler bei Janos Analyse: {e}"

    def render_ui(self, api_key=None):
        st.subheader(f"🤖 {self.name} - {self.description}")
        st.write("Analysiert die globale Makro-Lage, Zyklen, Zinsen und den VIX via Top-Down-Ansatz. Modell: gemini-3.6-flash")

        if st.button(f"Makro-Analyse starten ({self.name})", key=f"btn_run_{self.name}"):
            with st.spinner(f"{self.name} holt Makro-Daten und analysiert die Märkte..."):
                success, msg = self.run_analysis(api_key)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)

        st.markdown("---")
        st.markdown("### 📄 Letzter Makro-Report von Jano")
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
                st.info("Noch kein Bericht von Jano vorhanden.")
        except Exception as e:
            st.warning(f"Fehler beim Laden des Berichts aus Supabase: {e}")


# --- MODUL-EBENE FUNKTION ---
def render_ui(supabase_client, api_key=None):
    agent = JanoMacroAnalyst(supabase_client)
    agent.render_ui(api_key)