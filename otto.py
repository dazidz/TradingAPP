import pandas as pd
import yfinance as yf

class Employee:
    """Basis-Klasse für alle KI-Mitarbeiter"""
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Basis Mitarbeiter"
        self.description = "Keine Beschreibung"

    def run_analysis(self):
        raise NotImplementedError

    def get_logs(self):
        try:
            response = self.supabase.table(self.table_name).select("*").order("analysis_date", desc=True).limit(5).execute()
            return response.data
        except Exception:
            return []

    def save_feedback(self, feedback_text):
        try:
            res = self.supabase.table(self.table_name).select("id").order("analysis_date", desc=True).limit(1).execute()
            if res.data:
                latest_id = res.data[0]['id']
                self.supabase.table(self.table_name).update({"user_feedback": feedback_text}).eq("id", latest_id).execute()
                return True, "Feedback erfolgreich gespeichert."
            return False, "Kein Bericht vorhanden."
        except Exception as e:
            return False, str(e)


class OttoAnalyst(Employee):
    def __init__(self, supabase_client):
        super().__init__(supabase_client)
        self.name = "Otto (History Analyst)"
        self.description = "Analysiert langfristige historische Muster, Zinsstrukturen und Dalio-Zyklusphasen."
        self.table_name = "employee_otto_memory"

    def run_analysis(self):
        try:
            # Dalio Makro-Check
            macro_symbols = {"Zins": "^TNX", "Gold": "GC=F", "Öl": "CL=F"}
            macro_data = {}
            
            for name, sym in macro_symbols.items():
                df_m = yf.download(sym, period="6mo", progress=False, auto_adjust=True)
                if not df_m.empty:
                    close_col = df_m['Close']
                    if isinstance(close_col, pd.DataFrame):
                        close_col = close_col.iloc[:, 0]
                    curr = float(close_col.iloc[-1])
                    prev_6m = float(close_col.iloc[0])
                    pct = ((curr - prev_6m) / prev_6m) * 100
                    macro_data[name] = {"curr": curr, "pct": pct}

            response_wl = self.supabase.table("watchlist").select("ticker, company_name, sector").execute()
            df_wl = pd.DataFrame(response_wl.data)
            
            cycle_phase = "Unbekannt"
            analysis_text = ""
            
            if macro_data:
                zins_trend = macro_data.get("Zins", {}).get("pct", 0)
                gold_trend = macro_data.get("Gold", {}).get("pct", 0)
                
                if zins_trend > 5 and gold_trend > 0:
                    cycle_phase = "Spätzyklische Überhitzung / Inflationsdruck"
                    analysis_text = "Nach Dalio: Steigende Zinsen und fester Goldpreis signalisieren Inflationsdruck. Sachwerte bevorzugen."
                elif zins_trend < -5:
                    cycle_phase = "Reflation / Lockerung (Zentralbank-Stimulus)"
                    analysis_text = "Klassische Reflationsphase nach Dalio: Sinkende Zinsen entlasten die Verschuldung. Ideal für Wachstumswerte."
                else:
                    cycle_phase = "Schuldendynamische Konsolidierung (Seitwärtsphase)"
                    analysis_text = "Durch Schuldenzyklen erzwungene Seitwärtsphase. Selektiver Stockpicker-Markt."

            if not df_wl.empty:
                tickers = df_wl['ticker'].dropna().unique().tolist()
                df_hist = yf.download(tickers, period="1y", progress=False, auto_adjust=True)
                if not df_hist.empty:
                    analysis_text += f"\n\n*Watchlist-Basis:* {len(tickers)} Titel im historischen Screening geprüft."

            self.supabase.table(self.table_name).insert({
                "market_phase": cycle_phase,
                "insight": analysis_text
            }).execute()

            return True, "Analyse erfolgreich durchgeführt und im Gedächtnis verankert."
        except Exception as e:
            return False, str(e)