from datetime import datetime
from db import get_db_client
import pandas as pd


class ArisPerformanceManager:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.model_name = "openai/gpt-oss-120b"  # Zugewiesenes KI-Modell
    self.table_aris_arbeitsspeicher = "aris_arbeitsspeicher"
    self.table_principals = "principals"
    self.table_agent_reports = "agent_reports"

  def analyze_and_optimize(self):
    print(
        f"Aris (Performance Manager [{self.model_name}]) analysiert den"
        " Arbeitsspeicher..."
    )
    try:
      # 1. Daten aus aris_arbeitsspeicher holen
      res = (
          self.supabase.table(self.table_aris_arbeitsspeicher)
          .select("*")
          .execute()
      )
      items = res.data or []

      if not items:
        print("Keine Einträge im aris_arbeitsspeicher gefunden.")
        return

      df = pd.DataFrame(items)

      if "end_performance_5_tage" not in df.columns:
        print("Nicht genügend Performance-Daten im Arbeitsspeicher vorhanden.")
        return

      df["end_performance_5_tage"] = pd.to_numeric(
          df["end_performance_5_tage"], errors="coerce"
      )
      df["max_performance_5_tage"] = pd.to_numeric(
          df.get("max_performance_5_tage", 0), errors="coerce"
      )
      df["adx"] = pd.to_numeric(df.get("adx"), errors="coerce")

      # --- ANALYSE & KENNZAHLEN ---
      avg_end_perf = df["end_performance_5_tage"].mean()
      avg_max_perf = df["max_performance_5_tage"].mean()

      signal_groups = (
          df.groupby("signal_typ")["end_performance_5_tage"]
          .agg(["count", "mean"])
          .reset_index()
      )

      best_signal_type, best_signal_mean = "N/A", 0
      if not signal_groups.empty:
        best_row = signal_groups.loc[signal_groups["mean"].idxmax()]
        best_signal_type = str(best_row["signal_typ"])
        best_signal_mean = float(best_row["mean"])

      df["high_adx"] = df["adx"] > 25
      adx_groups = (
          df.groupby("high_adx")["end_performance_5_tage"].mean().to_dict()
      )

      # --- KOMPAKTE BULLET-POINTS (Token-optimiert für Joris) ---
      bullet_points = [
          f"Trades ausgewertet: {len(df)}",
          f"Ø Performance (Ende 5T): {avg_end_perf:.2f}% (Max: {avg_max_perf:.2f}%)",
          f"Top Signal: {best_signal_type} (Ø {best_signal_mean:.2f}%)",
          f"ADX-Trend: ADX>25 bringt Ø {adx_groups.get(True, 0):.2f}% vs. ADX<=25 mit Ø {adx_groups.get(False, 0):.2f}%",
      ]

      # Kompakter Fließtext für die bestehende report_content Spalte
      report_text = f"Trades: {len(df)} | Ø End: {avg_end_perf:.2f}% | Top Signal: {best_signal_type} ({best_signal_mean:.2f}%)"

      # 2. In die bestehende Tabelle 'agent_reports' schreiben
      report_payload = {
          "agent_name": "Aris",
          "report_content": report_text,
          "bullet_points": bullet_points,
      }
      self.supabase.table(self.table_agent_reports).insert(
          report_payload
      ).execute()
      print("✅ Kompakter Report mit Bullet-Points in 'agent_reports' abgelegt.")

      # 3. Erkenntnisse in 'principals' speichern
      principal_entry = {
          "datum": datetime.now().strftime("%Y-%m-%d"),
          "manager": "Aris",
          "ki_modell": self.model_name,
          "erkenntnisse": f"Bester Signal-Typ: {best_signal_type} ({best_signal_mean:.2f}%). ADX-Filter optimiert.",
          "status aktiv": True,
      }
      self.supabase.table(self.table_principals).insert(
          principal_entry
      ).execute()
      print("✅ Erkenntnisse in 'principals' gespeichert.")

      # 4. aris_arbeitsspeicher nach erfolgreicher Analyse bereinigen
      item_ids = [item["id"] for item in items if "id" in item]
      for item_id in item_ids:
        self.supabase.table(self.table_aris_arbeitsspeicher).delete().eq(
            "id", item_id
        ).execute()
      print("🧹 aris_arbeitsspeicher erfolgreich bereinigt.")

    except Exception as e:
      print(f"❌ Fehler in Aris Analyse: {e}")

  def run_all(self):
    self.analyze_and_optimize()


if __name__ == "__main__":
  supabase_client = get_db_client()
  aris = ArisPerformanceManager(supabase_client)
  aris.run_all()