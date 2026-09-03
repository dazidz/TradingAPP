import pandas as pd
import yfinance as yf
from datetime import datetime

class Employee:
    """Basis-Klasse für alle KI-Mitarbeiter im VisionDZ-Ökosystem."""
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Basis Mitarbeiter"
        self.description = "Keine Beschreibung"
        self.table_name = ""

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
                return True, "Feedback erfolgreich im Gedächtnis verankert."
            return False, "Kein Bericht vorhanden, an den das Feedback angehängt werden kann."
        except Exception as e:
            return False, str(e)


class OttoAnalyst(Employee):
    def __init__(self, supabase_client):
        super().__init__(supabase_client)
        self.name = "Otto (History Analyst)"
        self.description = "Analysiert langfristige historische Muster, Zinsstrukturen und Ray-Dalio-Wirtschaftszyklen."
        self.table_name = "employee_otto_memory"

    def run_analysis(self):
        try:
            # 1. Makro-Indikatoren als Dalio-Zyklus-Tacho laden (^TNX = Zins, GC=F = Gold, CL=F = Öl)
            macro_symbols = {"Zins": "^TNX", "Gold": "GC=F", "Öl": "CL=F"}
            macro_data = {}
            
            for name, sym in macro_symbols.items():
                df_m = yf.download(sym, period="1y", progress=False, auto_adjust=True)
                if not df_m.empty:
                    close_col = df_m['Close']
                    if isinstance(close_col, pd.DataFrame):
                        close_col = close_col.iloc[:, 0]
                    curr = float(close_col.iloc[-1])
                    prev_1y = float(close_col.iloc[0])
                    pct = ((curr - prev_1y) / prev_1y) * 100
                    macro_data[name] = {"curr": curr, "pct": pct}

            # 2. Watchlist aus Supabase laden
            response_wl = self.supabase.table("watchlist").select("ticker, company_name, sector").execute()
            df_wl = pd.DataFrame(response_wl.data)
            
            cycle_phase = "Unbekannt"
            macro_insight = ""
            
            # Dalio-Zyklus-Matrix anwenden
            if macro_data:
                zins_trend = macro_data.get("Zins", {}).get("pct", 0)
                gold_trend = macro_data.get("Gold", {}).get("pct", 0)
                
                if zins_trend > 5 and gold_trend > 0:
                    cycle_phase = "Spätzyklische Überhitzung / Inflationsdruck"
                    macro_insight = (
                        f"**Dalio-Makro-Analyse:** Steigende Zinsen ({zins_trend:+.1f}%) und fester Goldpreis ({gold_trend:+.1f}%) "
                        "signalisieren späten Zyklus und Inflationsdruck. Schuldenlasten wirken dämpfend, Sachwerte bevorzugen."
                    )
                elif zins_trend < -5:
                    cycle_phase = "Reflation / Zentralbank-Stimulus"
                    macro_insight = (
                        f"**Dalio-Makro-Analyse:** Sinkende Zinsen ({zins_trend:+.1f}%) entlasten die Verschuldung. "
                        "Klassische Reflationsphase, historisch starker Nährboden für Wachstum und Aktien-Rallies."
                    )
                else:
                    cycle_phase = "Schuldendynamische Konsolidierung"
                    macro_insight = (
                        f"**Dalio-Makro-Analyse:** Moderater Zinstrend ({zins_trend:+.1f}%). "
                        "Die Märkte bewegen sich in einer durch historische Schuldenzyklen erzwungenen Seitwärts- und Selektionsphase."
                    )

            # 3. Langfristige historische Muster über die Watchlist scannen (1 Jahr Historie)
            pattern_details = []
            if not df_wl.empty:
                tickers = df_wl['ticker'].dropna().unique().tolist()
                df_hist = yf.download(tickers, period="1y", progress=False, auto_adjust=True)
                
                if not df_hist.empty:
                    df_close = df_hist['Close'] if isinstance(df_hist.columns, pd.MultiIndex) else df_hist[['Close']]
                    
                    bullish_count = 0
                    bearish_count = 0
                    
                    for ticker in tickers:
                        try:
                            series = df_close[ticker].dropna() if isinstance(df_close, pd.DataFrame) else df_close.dropna()
                            if len(series) > 50:
                                p_curr = float(series.iloc[-1])
                                sma_50 = float(series.rolling(window=50).mean().iloc[-1])
                                high_52w = float(series.max())
                                
                                c_name = df_wl.loc[df_wl['ticker'] == ticker, 'company_name'].values[0]
                                
                                # Muster: Ausbruch nahe 52W-Hoch über SMA50
                                if p_curr > sma_50 and p_curr >= (high_52w * 0.95):
                                    bullish_count += 1
                                    if len(pattern_details) < 3:
                                        pattern_details.append(f"• **{c_name}**: Historisches Breakout-Muster (nahe 52W-Hoch bei {high_52w:.2f}).")
                                elif p_curr < sma_50:
                                    bearish_count += 1
                        except Exception:
                            continue
                    
                    macro_insight += f"\n\n**Muster-Screening:** {bullish_count} Titel in historischer Stärke (über SMA50 & nahe 52W-Hoch), {bearish_count} Titel unter Druck."
                    if pattern_details:
                        macro_insight += "\n" + "\n".join(pattern_details)

            # 4. In Ottos Supabase-Gedächtnis abspeichern
            self.supabase.table(self.table_name).insert({
                "market_phase": cycle_phase,
                "insight": macro_insight
            }).execute()

            return True, "Otto hat die historischen Zyklen und Watchlist-Muster erfolgreich analysiert und im Langzeitgedächtnis verankert."
        except Exception as e:
            return False, f"Fehler bei Ottos Analyse: {e}"