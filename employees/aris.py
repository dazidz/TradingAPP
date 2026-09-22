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
        f"Aris (Technischer Screener [{self.model_name}]) analysiert den"
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

      # Numerische Konvertierung für technische Indikatoren (z.B. ADX)
      df["adx"] = pd.to_numeric(df.get("adx"), errors="coerce")

      # --- TECHNISCHE ANALYSE & KENNZAHLEN ---
      total_signals = len(df)

      # Häufigkeit der Signal-Typen ermitteln
      signal_counts = (
          df["signal_typ"].value_counts().reset_index()
          if "signal_typ" in df.columns
          else pd.DataFrame()
      )
      top_signal_type = (
          str(signal_counts.iloc[0]["signal_typ"])
          if not signal_counts.empty
          else "N/A"
      )
      top_signal_count = (
          int(signal_counts.iloc[0]["count"]) if not signal_counts.empty else 0
      )

      # ADX-Trendverteilung prüfen
      df["high_adx"] = df["adx"] > 25 if "adx" in df.columns else False
      high_adx_count = int(df["high_adx"].sum())

      # --- KOMPAKTE BULLET-POINTS (Token-optimiert für Joris) ---
      bullet_points = [
          f"Analysierte Signale/Setups: {total_signals}",
          (
              f"Häufigster Signal-Typ: {top_signal_type} ({top_signal_count}"
              " mal)"
          ),
          (
              f"ADX-Trendfilter: {high_adx_count} von {total_signals} Signalen"
              " mit starkem Trend (ADX > 25)"
          ),
      ]

      # Kompakter Fließtext für die bestehende report_content Spalte
      report_text = f"Signale analysiert: {total_signals} | Top Signal: {top_signal_type} ({top_signal_count}x) | Starker Trend (ADX>25): {high_adx_count}"

      # 2. In die bestehende Tabelle 'agent_reports' schreiben
      report_payload = {
          "agent_name": "Aris",
          "report_content": report_text,
          "bullet_points": bullet_points,
          "status": "unread",
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
          "erkenntnisse": (
              f"Technische Signale ausgewertet: {total_signals} Signale."
              f" Dominanter Typ: {top_signal_type}."
          ),
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