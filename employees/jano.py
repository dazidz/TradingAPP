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
        Du bist Jano, der leitende Makro-Analyst in unserem Investment-Team. Deine Brille ist strikt Top-Down. 
        Du analysierst die globale Großwetterlage: Zinsen, Zinskurven, den VIX (Volatilitätsindex), Rohstoffe (Öl, Gold etc.) und breite Marktindizes (S&P 500, Nasdaq).
        
        Deine Aufgabe:
        1. Bestimme die aktuelle Marktphase (z.B. Bullenmarkt, Korrektur, Hochvolatiler Übergang, Rezessionsangst).
        2. Leite daraus ab, wie aggressiv oder defensiv wir agieren sollten.
        3. Fasse deine Erkenntnisse prägnant und datenbasiert zusammen. Keine leeren Worthülsen.
        """

  def fetch_macro_data(self):
    """Holt aktuelle Makro-Indikatoren über yfinance."""
    tickers = {
        "S&P 500": "^GSPC",
        "Nasdaq 100": "^NDX",
        "VIX (Volatilität)": "^VIX",
        "10Y US Treasury Yield": "^TNX",
        "Gold": "GC=F",
        "Crude Oil": "CL=F",
    }

    macro_data = {}
    for name, ticker in tickers.items():
      try:
        df = yf.download(ticker, period="5d", progress=False)
        if not df.empty and "Close" in df:
          # Handle potential multi-index columns from yfinance
          close_series = (
              df["Close"].iloc[:, 0]
              if isinstance(df["Close"], pd.DataFrame)
              else df["Close"]
          )
          current = float(close_series.iloc[-1])
          previous = float(close_series.iloc[-2])
          change = ((current - previous) / previous) * 100
          macro_data[name] = {
              "aktuell": round(current, 2),
              "änderung_%": round(change, 2),
          }
      except Exception:
        continue

    return macro_data

  def run_analysis(self):
    """Führt die Makro-Analyse mit Gemini durch und speichert sie in Supabase."""
    try:
      # API Key aus Streamlit Secrets (wird vorausgesetzt, dass streamlit im Scope ist oder via init übergeben wird)
      import streamlit as st

      api_key = st.secrets["GEMINI_API_KEY"]
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

      insight_text = response.text
      today_str = datetime.now().strftime("%Y-%m-%d")

      # Marktphase extrahieren oder standardmäßig setzen
      market_phase = "Neutral / Unbekannt"
      if "Bullenmarkt" in insight_text:
        market_phase = "Bullenmarkt"
      elif "Korrektur" in insight_text:
        market_phase = "Korrektur"
      elif "High Volatility" in insight_text or "Volatil" in insight_text:
        market_phase = "Hohe Volatilität"

      # In Supabase speichern (Tabelle: macro_logs)
      self.supabase.table("macro_logs").insert({
          "analysis_date": today_str,
          "market_phase": market_phase,
          "insight": insight_text,
      }).execute()

      return True, "Jano hat die Makro-Analyse erfolgreich abgeschlossen."
    except Exception as e:
      return False, f"Fehler bei Janos Analyse: {e}"

  def get_latest_log(self):
    """Holt den neuesten Makro-Log aus Supabase."""
    try:
      res = (
          self.supabase.table("macro_logs")
          .select("*")
          .order("analysis_date", desc=True)
          .limit(1)
          .execute()
      )
      return res.data[0] if res.data else None
    except Exception:
      return None