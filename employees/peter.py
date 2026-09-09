from datetime import datetime
import google.generativeai as genai
import pandas as pd
import yfinance as yf


class PeterInsiderAnalyst:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Peter"
        self.description = (
            "Micro-Analyst (Einzelunternehmen, Fundamentaldaten, News, Insider)"
        )

        self.peter_dna = (
            "Du bist Peter, der leitende Micro- und Insider-Analyst in unserem Team. "
            "Deine Brille ist strikt Bottom-Up. Du analysierst Einzelwerte, Top "
            "Investoren Aktionen, Branchen-News und Insider-Transaktionen.\n\n"
            "WICHTIG - FUNDAMENTAL-FEED PRÄZISION:\n"
            "Du verlangst harte Fakten. Achte besonders auf:\n"
            "1. Was kaufen in letzter Zeit die Top Investoren, gibt es Gemeinsamkeiten?\n"
            "2. Welche Unternehmen aus der Watchlist sind aktuell vermehrt in den Nachrichten?\n"
            "3. Insider-Aktivitäten: Kaufen oder verkaufen die Manager?\n"
            "4. Gibt es Gemeinsamkeiten bei Top Investoren, Insideraktivitäten und Nachrichten?\n\n"
            "Fasse deine Erkenntnisse prägnant, kritisch und faktenbasiert zusammen. "
            "Kein Schönreden von schwachen Bilanzen."
        )

    def fetch_bottom_up_data(self):
        """Platzhalter – falls diese Methode extern geholt wird, hier anpassen."""
        # Beispielhafter Rückgabewert, falls die Methode in deiner Architektur woanders liegt
        return "Hier die aktuellen Fundamentaldaten der Watchlist..."

    def run_analysis(self, api_key: str):
        """Führt die Peter-Analyse aus und speichert sie zentral in agent_reports."""
        try:
            if not api_key:
                return False, "Kein gültiger API-Key übergeben."

            genai.configure(api_key=api_key)

            fundamental_context = self.fetch_bottom_up_data()

            context = (
                "--- WATCHLIST FUNDAMENTALS & BILANZ-METRIKEN "
                f"(TTM-KGV, FCF, NET DEBT) ---\n{fundamental_context}"
            )

            # Korrekte Initialisierung für Gemini-Modelle
            model = genai.GenerativeModel(
                model_name="gemini-3.6-flash",
                system_instruction=self.peter_dna,
            )
            response = model.generate_content(
                "Analysiere die Fundamentaldaten, insbesondere TTM-KGV, "
                f"FCF-Rendite und den Verschuldungsgrad der Watchlist-Werte:\n\n{context}"
            )

            report_content = response.text
            today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

            self.supabase.table("agent_reports").insert({
                "agent_name": self.name,
                "report_content": f"**Report vom {today_str}:**\n\n{report_content}",
            }).execute()

            return (
                True,
                "Peter hat die Micro-Analyse mit bereinigten Kennzahlen abgeschlossen.",
            )
        except Exception as e:
            return False, f"Fehler bei Peters Analyse: {e}"

    def fetch_market_intel(self, api_key: str):
        """Alias zur Kompatibilität, reicht den Key direkt weiter."""
        return self.run_analysis(api_key)

    def get_latest_report(self):
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

    def get_latest_intel(self):
        res = self.get_latest_report()
        if res:
            return {
                "analysis_date": res.get("created_at", "N/A")[:16],
                "insider_activity": res.get("report_content"),
                "analyst_consensus": "Siehe Hauptbericht",
                "market_news_summary": "Siehe Hauptbericht",
            }
        return None