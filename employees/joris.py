from datetime import datetime
import pandas as pd


class JorisPortfolioManager:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Joris"
    self.description = (
        "Watchlist-Performance, Setup-Transfer & Watchlist Performer"
    )

  def run_transfer_routine(self):
    """Führt Joris gesamte Hintergrund-Routine aus:

    1. Übertragung von max_performance_5_tage und setup_reason in den
    Arbeitsspeicher.
    2. Ermittlung und Speicherung der Top 5 & Flop 5 Performer der Watchlist.
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
        # Prüfen, ob bereits übertragen (über das Flag aris_übertrag)
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
          # In den Arbeitsspeicher schreiben
          self.supabase.table("aris_arbeitsspeicher").insert(payload).execute()

          # Flag in der Quelletabelle aktualisieren, damit es nicht doppelt läuft
          self.supabase.table("joris_journal").update(
              {"aris_übertrag": True}
          ).eq("id", row["id"]).execute()

    except Exception as e:
      print(f"Fehler beim Performance- und Setup-Transfer durch Joris: {e}")

  def process_watchlist_performers(self):
    """Ermittelt aus der Supabase-Tabelle 'watchlist' die Top 5 und Flop 5

    Performer des Tages und speichert diese im Arbeitsspeicher ab.
    """
    try:
      response = self.supabase.table("watchlist").select("*").execute()
      data = response.data

      if not data:
        return

      df = pd.DataFrame(data)

      # Automatische Erkennung der Performance-Spalte
      perf_column = None
      for col in ["change_percent", "daily_change", "performance", "perf_1d"]:
        if col in df.columns:
          perf_column = col
          break

      if perf_column and not df.empty:
        df[perf_column] = pd.to_numeric(df[perf_column], errors="coerce")
        df = df.dropna(subset=[perf_column])

        df_sorted = df.sort_values(by=perf_column, ascending=False)

        top_5 = df_sorted.head(5)
        flop_5 = df_sorted.tail(5)

        today_str = datetime.now().strftime("%Y-%m-%d")
        symbol_col = "symbol" if "symbol" in df.columns else df.columns[0]

        payload = {
            "datum": today_str,
            "top_5": top_5[[symbol_col, perf_column]].to_dict(
                orient="records"
            ),
            "flop_5": flop_5[[symbol_col, perf_column]].to_dict(
                orient="records"
            ),
        }

        self.supabase.table("aris_arbeitsspeicher").insert({
            "kategorie": "watchlist_ranking",
            "report_content": (
                f"Watchlist Top/Flop Ranking vom {today_str}:\n{str(payload)}"
            ),
            "created_at": datetime.now().isoformat(),
        }).execute()

    except Exception as e:
      print(f"Fehler bei der Watchlist-Auswertung durch Joris: {e}")

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

  def get_latest_report(self):
    """Ruft den neuesten Bericht oder Eintrag aus dem Arbeitsspeicher ab."""
    try:
      res = (
          self.supabase.table("aris_arbeitsspeicher")
          .select("*")
          .order("created_at", desc=True)
          .limit(1)
          .execute()
      )
      if res.data:
        return res.data[0]
      return None
    except Exception as e:
      print(f"Fehler beim Laden des neuesten Reports durch Joris: {e}")
      return None