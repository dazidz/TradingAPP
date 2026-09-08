from datetime import datetime
import google.generativeai as genai
import pandas as pd
import yfinance as yf


class OttoAnalyst:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Otto"
    self.description = (
        "History & Patterns Analyst (Muster-Matching, historische"
        " Korrelationen, analoge Börsenphasen)"
    )

    self.otto_dna = """
        Du bist Otto, der leitende Historien- und Muster-Analyst in unserem Team. Deine Brille ist strikt quantitativ-historisch.
        Du vergleichst aktuelle Marktphasen, Volatilitäten und Zinsumfelder mit historischen Krisen, Blasen und Boom-Phasen (z.B. 2000, 2008, 2020, 2022).
        
        Deine Aufgabe:
        1. Analysiere historische Muster anhand von Kurs- und Volatilitätsdaten.
        2. Zeige Parallelen und Unterschiede zu früheren Börsenzyklen auf.
        3. Warne vor historischen Fallen oder bestätige historische Chancen faktenbasiert.
        """

  def fetch_historical_context(self):
    """Holt historische S&P 500 Daten für das Muster-Matching."""
    try:
      t = yf.Ticker("^GSPC")
      hist = t.history(period="5y")
      if hist.empty:
        return "Keine historischen Daten verfügbar."

      recent_close = hist["Close"].iloc[-1]
      high_1y = hist["Close"].tail(252).max()
      low_1y = hist["Close"].tail(252).min()

      return (
          f"S&P 500 aktueller Stand: {recent_close:.2f}\n1-Jahres-Hoch:"
          f" {high_1y:.2f}\n1-Jahres-Tief: {low_1y:.2f}"
      )
    except Exception as e:
      return f"Fehler beim Laden historischer Daten: {e}"

  def run_analysis(self, api_key: str):
    """Führt Ottos historische Muster-Analyse aus und speichert sie in agent_reports."""
    try:
      genai.configure(api_key=api_key)

      history_context = self.fetch_historical_context()

      context = f"""
            --- HISTORISCHER KONTEXT & MARKT-MUSTER ---
            {history_context}
            """

      model = genai.GenerativeModel(
          model_name="gemini-3.6-flash", system_instruction=self.otto_dna
      )
      response = model.generate_content(
          "Führe ein historisches Muster-Matching und einen"
          f" Zyklus-Vergleich durch:\n\n{context}"
      )

      report_content = response.text
      today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

      # Zentral in agent_reports speichern
      self.supabase.table("agent_reports").insert({
          "agent_name": self.name,
          "report_content": f"**Report vom {today_str}:**\n\n{report_content}",
      }).execute()

      return (
          True,
          "Otto hat die historische Muster-Analyse erfolgreich abgeschlossen.",
      )
    except Exception as e:
      return False, f"Fehler bei Ottos Analyse: {e}"

  def get_latest_report(self):
    """Holt den neuesten Bericht von Otto aus der zentralen Tabelle."""
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