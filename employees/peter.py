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

    self.peter_dna = """
        Du bist Peter, der leitende Micro- und Insider-Analyst in unserem Team. Deine Brille ist strikt Bottom-Up.
        Du analysierst Einzelwerte, fundamentale Kennzahlen, Branchen-News und Insider-Transaktionen (Käufe/Verkäufe von C-Level-Managern und großen institutionellen Haltern).
        
        Deine Aufgabe:
        1. Bewerte die Fundamentaldaten und das Momentum konkreter Watchlist- oder Depot-Kandidaten.
        2. Achte besonders auf Insider-Signale: Kaufen die Manager mit ihrem eigenen Geld oder verkaufen sie massiv?
        3. Fasse deine Erkenntnisse prägnant, kritisch und faktenbasiert zusammen. Kein Schönreden von schwachen Bilanzstrukturen.
        """

  def fetch_bottom_up_data(self):
    """Holt grundlegende Kennzahlen für die Watchlist über yfinance."""
    try:
      watchlist_res = self.supabase.table("watchlist").select("*").execute()
      watchlist_df = pd.DataFrame(watchlist_res.data)

      if watchlist_df.empty or "ticker" not in watchlist_df.columns:
        return "Keine Watchlist-Einträge gefunden."

      summaries = []
      for _, row in watchlist_df.head(15).iterrows():  # Limit auf Top 15 für Performance
        ticker = row.get("ticker")
        try:
          t = yf.Ticker(ticker)
          info = t.info
          summaries.append({
              "Ticker": ticker,
              "Name": info.get("shortName", ticker),
              "Sektor": info.get("sector", "N/A"),
              "KGV (Trailing)": info.get("trailingPE", "N/A"),
              "Gewinnwachstum": info.get("earningsGrowth", "N/A"),
              "Insider-Held-%": info.get("heldPercentInsiders", "N/A"),
          })
        except Exception:
          continue

      return (
          pd.DataFrame(summaries).to_string()
          if summaries
          else "Keine Fundamental-Daten abrufbar."
      )
    except Exception as e:
      return f Fehler beim Laden der Watchlist: {e}"

  def run_analysis(self):
    """Führt die Peter-Analyse aus und speichert sie zentral in agent_reports."""
    try:
      import streamlit as st

      api_key = st.secrets["GEMINI_API_KEY"]
      genai.configure(api_key=api_key)

      fundamental_context = self.fetch_bottom_up_data()

      context = f"""
            --- WATCHLIST FUNDAMENTALS & INSIDER-DATEN ---
            {fundamental_context}
            """

      model = genai.GenerativeModel(
          model_name="gemini-3.6-flash", system_instruction=self.peter_dna
      )
      response = model.generate_content(
          "Analysiere die Fundamentaldaten und Insider-Aktivitäten der"
          f" Watchlist-Werte:\n\n{context}"
      )

      report_content = response.text
      today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

      # Zentral in agent_reports speichern
      self.supabase.table("agent_reports").insert({
          "agent_name": self.name,
          "report_content": f"**Report vom {today_str}:**\n\n{report_content}",
      }).execute()

      return True, "Peter hat die Micro-Analyse erfolgreich abgeschlossen."
    except Exception as e:
      return False, f"Fehler bei Peters Analyse: {e}"

  def get_latest_report(self):
    """Holt den neuesten Bericht von Peter aus der zentralen Tabelle."""
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