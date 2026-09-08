from datetime import datetime
import google.generativeai as genai
import pandas as pd
import yfinance as yf


class JanoMacroAnalyst:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Jano"
    self.description = (
        "Makro-Analyst (Zyklen, Zinsen, VIX, Rohstoffe, Top-Down)"
    )

    self.jano_dna = """
        Du bist Jano, der leitende Makro-Analyst in unserem Team. Deine Brille ist strikt Top-Down.
        Du analysierst Zyklen, Zinsen, den VIX, Rohstoffe, globale Liquidität und die übergeordnete Marktphase (Bullenmarkt, Bärenmarkt, Seitwärtsphase/Korrektur).
        
        Deine Aufgabe:
        1. Bewerte die aktuelle makroökonomische Großwetterlage anhand der gelieferten Kennzahlen.
        2. Leite daraus ab, welches Marktumfeld wir aktuell haben und ob Risiko-Assets (wie Aktien) Rückenwind oder Gegenwind haben.
        3. Fasse deine Erkenntnisse prägnant, analytisch und ungeschönt zusammen.
        """

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

  def run_analysis(self, api_key: str):
    """Führt die Makro-Analyse aus und speichert sie zentral in agent_reports."""
    try:
      # Gemini mit dem übergebenen Key konfigurieren
      genai.configure(api_key=api_key)

      macro_metrics = self.fetch_macro_data()
      df_macro = pd.DataFrame(macro_metrics).T

      context = f"""
            --- AKTUELLE MAKRO-DATEN (YFINANCE) ---
            {df_macro.to_string() if not df_macro.empty else "Keine Daten abrufbar"}
            """

      model = genai.GenerativeModel(
          model_name="gemini-3.6-flash", system_instruction=self.jano_dna
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

  def get_latest_report(self):
    """Holt den neuesten Bericht von Jano aus der zentralen Tabelle."""
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