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
        Du analysierst Einzelwerte, fundamentale Kennzahlen, Branchen-News und Insider-Transaktionen.
        
        WICHTIG - FUNDAMENTAL-FEED PRÄZISION:
        Du verlangst harte Fakten. Achte besonders auf:
        1. TTM-KGV (Trailing Price-to-Earnings): Bewertung auf Basis der letzten 12 Monate.
        2. FCF-Rendite (Free Cash Flow Yield): Wie viel Cash generiert das Unternehmen im Verhältnis zur Marktkapitalisierung?
        3. Verschuldungsgrad (Net Debt / EBITDA): Ist die Bilanz gesund oder droht Überschuldung?
        4. Insider-Aktivitäten: Kaufen oder verkaufen die Manager?
        
        Fasse deine Erkenntnisse prägnant, kritisch und faktenbasiert zusammen. Kein Schönreden von schwachen Bilanzen.
        """

  def fetch_bottom_up_data(self):
    """Holt echte TTM-KGVs, FCF-Renditen und Verschuldungsgrade über yfinance."""
    try:
      watchlist_res = self.supabase.table("watchlist").select("*").execute()
      watchlist_df = pd.DataFrame(watchlist_res.data)

      if watchlist_df.empty or "ticker" not in watchlist_df.columns:
        return "Keine Watchlist-Einträge gefunden."

      summaries = []
      for _, row in watchlist_df.head(15).iterrows():
        ticker = row.get("ticker")
        try:
          t = yf.Ticker(ticker)
          info = t.info

          pe_ttm = info.get("trailingPE", "N/A")

          fcf = info.get("freeCashflow")
          mcap = info.get("marketCap")
          fcf_yield = "N/A"
          if fcf and mcap and mcap > 0:
            fcf_yield = f"{round((fcf / mcap) * 100, 2)}%"

          total_debt = info.get("totalDebt", 0) or 0
          total_cash = info.get("totalCash", 0) or 0
          ebitda = info.get("ebitda")
          net_debt_ebitda = "N/A"
          if ebitda and ebitda > 0:
            net_debt = total_debt - total_cash
            net_debt_ebitda = round(net_debt / ebitda, 2)

          summaries.append({
              "Ticker": ticker,
              "Name": info.get("shortName", ticker),
              "Sektor": info.get("sector", "N/A"),
              "TTM-KGV": pe_ttm,
              "FCF-Rendite": fcf_yield,
              "Net Debt / EBITDA": net_debt_ebitda,
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
      return f"Fehler beim Laden der Watchlist: {e}"

  def run_analysis(self, api_key: str):
    """Führt die Peter-Analyse aus und speichert sie zentral in agent_reports."""
    try:
      if not api_key:
        return False, "Kein gültiger API-Key übergeben."

      genai.configure(api_key=api_key)

      fundamental_context = self.fetch_bottom_up_data()

      context = f"""
            --- WATCHLIST FUNDAMENTALS & BILANZ-METRIKEN (TTM-KGV, FCF, NET DEBT) ---
            {fundamental_context}
            """

      model = genai.GenerativeModel(
          model_name="gemini-3.6-flash", system_instruction=self.peter_dna
      )
      response = model.generate_content(
          "Analysiere die Fundamentaldaten, insbesondere TTM-KGV, FCF-Rendite"
          f" und den Verschuldungsgrad der Watchlist-Werte:\n\n{context}"
      )

      report_content = response.text
      today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

      self.supabase.table("agent_reports").insert({
          "agent_name": self.name,
          "report_content": f"**Report vom {today_str}:**\n\n{report_content}",
      }).execute()

      return (
          True,
          "Peter hat die Micro-Analyse mit bereinigten Kennzahlen"
          " abgeschlossen.",
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