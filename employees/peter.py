from datetime import datetime
import google.generativeai as genai
import pandas as pd
import yfinance as yf


class PeterInsiderAnalyst:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Peter"
    self.description = (
        "Micro-Analyst (Fokus: Top-Investoren, Insider-Aktionen & Live-News)"
    )

    self.peter_dna = (
        "Du bist Peter, der leitende Micro- und Insider-Analyst in unserem Team.\n"
        "Deine Brille ist strikt Bottom-Up. Du analysierst keine trockenen Bilanzen mehr,\n"
        "sondern konzentrierst dich voll auf:\n"
        "1. Top-Investoren-Aktionen & institutionelle Bewegungen.\n"
        "2. Insider-Transaktionen (Käufe/Verkäufe von Managern).\n"
        "3. Live-Branchen- und Unternehmens-News aus dem Markt.\n\n"
        "Fasse deine Erkenntnisse prägnant, kritisch und faktenbasiert zusammen. "
        "Decke Auffälligkeiten auf und zeige auf, wo Insider oder große Player "
        "aggressiv kaufen oder abverkaufen."
    )

  def fetch_live_market_data(self):
    """Holt live News und verfügbare Insider-Infos via yfinance für eine Watchlist."""
    # Beispiel-Watchlist – du kannst hier deine eigenen Ticker dynamisch aus Supabase laden
    watchlist = ["AAPL", "MSFT", "GOOGL", "NVDA", "AMZN", "TSLA"]

    compiled_data = ""

    for ticker_symbol in watchlist:
      try:
        tk = yf.Ticker(ticker_symbol)

        # 1. Live News abrufen
        news_list = tk.news
        news_summary = ""
        if news_list:
          # Nimm die letzten 3 Schlagzeilen
          recent_news = [
              item.get("title", "") for item in news_list[:3] if "title" in item
          ]
          news_summary = " | ".join(recent_news)
        else:
          news_summary = "Keine aktuellen News gefunden."

        # 2. Insider-Transaktionen / Käufe (soweit von yfinance bereitgestellt)
        insider_info = "Keine Details verfügbar"
        try:
          insider_df = tk.insider_purchases
          if insider_df is not None and not insider_df.empty:
            insider_info = insider_df.to_string()
        except Exception:
          pass

        compiled_data += f"\n--- TICKER: {ticker_symbol} ---\n"
        compiled_data += f"Letzte News: {news_summary}\n"
        compiled_data += f"Insider-Daten:\n{insider_info}\n"

      except Exception as e:
        compiled_data += f"\n--- TICKER: {ticker_symbol} (Fehler beim Laden: {e}) ---\n"

    return compiled_data

  def run_analysis(self, api_key: str):
    """Führt die Peter-Analyse mit Live-Daten aus und speichert sie in agent_reports."""
    try:
      if not api_key:
        return False, "Kein gültiger API-Key übergeben."

      genai.configure(api_key=api_key)

      # Live-Daten über yfinance abrufen
      live_context = self.fetch_live_market_data()

      context = (
          "--- LIVE NEWS & INSIDER-DATEN DER WATCHLIST ---\n" f"{live_context}"
      )

      # Verwende z.B. gemini-1.5-flash oder das von dir gewünschte Modell
      model = genai.GenerativeModel(
          model_name="gemini-1.5-flash", system_instruction=self.peter_dna
      )
      response = model.generate_content(
          "Analysiere die folgenden Live-News und Insider-Aktivitäten der"
          " Watchlist-Werte. Welche Signale senden die Manager und großen"
          f" Investoren?\n\n{context}"
      )

      report_content = response.text
      today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

      self.supabase.table("agent_reports").insert({
          "agent_name": self.name,
          "report_content": f"**Report vom {today_str}:**\n\n{report_content}",
      }).execute()

      return (
          True,
          "Peter hat die Live-Insider- und News-Analyse erfolgreich"
          " abgeschlossen.",
      )
    except Exception as e:
      return False, f"Fehler bei Peters Analyse: {e}"

  def fetch_market_intel(self, api_key: str):
    """Alias zur Kompatibilität."""
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