from datetime import datetime
import pandas as pd
import yfinance as yf


class LeopoldAssistant:

  def __init__(self, supabase_client):
    self.supabase = supabase_client

  def run_transfer_routine(self):
    """Führt Leopolds gesamte Hintergrund-Routine aus:

    1. Übertragung von max_performance_5_tage und setup_reason in den
    Arbeitsspeicher.
    2. Ermittlung und Speicherung der Top 5 & Flop 5 Performer der Watchlist via
    yfinance.
    """
    self._process_performance_transfer()
    self.process_watchlist_performers()

  def _process_performance_transfer(self):
    """Interne Methode für den Transfer von Performance und setup_reason."""
    try:
      response = (
          self.supabase.table("joris_journal")
          .select("*")
          .not_.is_("max_performance_5_tage", "null")
          .execute()
      )
      records = response.data

      if not records:
        return

      for row in records:
        if not row.get("aris_übertrag", False):
          symbol = row.get("symbol", "N/A")
          max_perf = row.get("max_performance_5_tage")
          setup_reason = row.get("setup_reason", "Kein Grund angegeben")

          payload = {
              "kategorie": "performance_and_setup_transfer",
              "report_content": (
                  f"Transfer für Symbol {symbol}:\n"
                  f"- Max-Perf 5T: {max_perf}\n"
                  f"- Setup Reason: {setup_reason}"
              ),
              "created_at": datetime.now().isoformat(),
          }
          self.supabase.table("aris_arbeitsspeicher").insert(payload).execute()

          self.supabase.table("joris_journal").update(
              {"aris_übertrag": True}
          ).eq("id", row["id"]).execute()

    except Exception as e:
      print(f"Fehler beim Performance- und Setup-Transfer durch Leopold: {e}")

  def process_watchlist_performers(self):
    """Lädt die Watchlist aus Supabase, holt die Live-Kurse via yfinance,

    berechnet die Tagesperformance und speichert Top 5 & Flop 5 im Arbeitsspeicher.
    """
    try:
      response = (
          self.supabase.table("watchlist")
          .select("ticker, company_name, gettex_ticker, sector")
          .execute()
      )
      data = response.data

      if not data:
        return

      df = pd.DataFrame(data)
      if df.empty:
        return

      performances = []
      for _, row in df.iterrows():
        try:
          ticker_obj = yf.Ticker(row["ticker"])
          info = ticker_obj.info
          curr = info.get("currentPrice") or info.get("regularMarketPrice")
          prev = info.get("previousClose")

          if curr and prev:
            change_pct = round(((curr - prev) / prev) * 100, 2)
            performances.append({
                "Firma": row["company_name"],
                "Ticker": row["ticker"],
                "Sektor": row.get("sector", "N/A"),
                "Aktuell": round(float(curr), 2),
                "Tageschange (%)": change_pct,
            })
        except Exception:
          continue

      if not performances:
        return

      df_perf = pd.DataFrame(performances)

      # Nach Tageschange sortieren
      df_sorted = df_perf.sort_values(by="Tageschange (%)", ascending=False)

      top_5 = df_sorted.head(5)
      flop_5 = df_sorted.tail(5)

      today_str = datetime.now().strftime("%Y-%m-%d")

      payload = {
          "datum": today_str,
          "top_5": top_5.to_dict(orient="records"),
          "flop_5": flop_5.to_dict(orient="records"),
      }

      self.supabase.table("aris_arbeitsspeicher").insert({
          "kategorie": "watchlist_ranking",
          "report_content": (
              f"Watchlist Top/Flop Ranking vom {today_str}:\n{str(payload)}"
          ),
          "created_at": datetime.now().isoformat(),
      }).execute()

    except Exception as e:
      print(f"Fehler bei der Watchlist-Auswertung durch Leopold: {e}")

  def get_aris_arbeitsspeicher_data(self):
    """Ruft die letzten Einträge aus dem Aris-Arbeitsspeicher ab."""
    try:
      res = (
          self.supabase.table("aris_arbeitsspeicher")
          .select("*")
          .order("created_at", desc=True)
          .limit(20)
          .execute()
      )
      return res.data
    except Exception as e:
      print(f"Fehler beim Laden des Arbeitsspeichers: {e}")
      return []