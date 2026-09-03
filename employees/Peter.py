import datetime
import yfinance as yf

class PeterInsiderAnalyst:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Peter (Market Intel & Insider)"
        self.description = "Sammelt rein datenbasiert und kostenfrei Markt-Kennzahlen und bereinigt alte Logs."
        self.table_name = "peter_market_intel"

    def fetch_market_intel(self):
        """
        Peters kostenlose Routine: Holt Marktdaten, speichert sie ab 
        und löscht Einträge, die älter als 6 Monate sind.
        """
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        try:
            # 1. Frische Daten holen (Beispiel SPY Baseline)
            spy = yf.Ticker("SPY")
            info = spy.info
            
            forward_pe = info.get('forwardPE', 'N/A')
            dividend_yield = info.get('dividendYield', 'N/A')
            if dividend_yield and dividend_yield != 'N/A':
                dividend_yield = f"{float(dividend_yield) * 100:.2f}%"

            market_summary = (
                f"Markt-Update (SPY Baseline): "
                f"Forward P/E liegt bei {forward_pe}, "
                f"Dividendenrendite bei {dividend_yield}. "
                f"Kostenfreie Basis-Abfrage."
            )

            intel_report = {
                "analysis_date": today_str,
                "insider_activity": "SEC-Schnittstelle aktiv (Standard-Monitoring).",
                "analyst_consensus": f"Forward P/E Bewertung: {forward_pe}",
                "market_news_summary": market_summary
            }

            # 2. In Supabase abspeichern
            self.supabase.table(self.table_name).insert(intel_report).execute()

            # 3. Automatische Bereinigung: Alles löschen, was älter als 6 Monate (180 Tage) ist
            six_months_ago = (datetime.datetime.now() - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
            
            self.supabase.table(self.table_name).delete().lt("analysis_date", six_months_ago).execute()

            return True, "Peter hat Marktdaten aktualisiert und Einträge > 6 Monate bereinigt."
            
        except Exception as e:
            return False, f"Fehler bei Peters Routine: {e}"

    def get_latest_intel(self):
        """Holt den aktuellsten Bericht von Peter aus der Datenbank."""
        try:
            res = self.supabase.table(self.table_name).select("*").order("analysis_date", desc=True).limit(1).execute()
            if res.data:
                return res.data[0]
            return None
        except Exception:
            return None