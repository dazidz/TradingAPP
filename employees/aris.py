from datetime import datetime
from db import get_db_client
from groq import Groq
import pandas as pd
import streamlit as st


class ArisPerformanceManager:

  def __init__(self, supabase_client, api_key: str = None):
    self.supabase = supabase_client
    self.model_name = (
        "llama-3.3-70b-versatile"  # Oder dein gewünschtes Groq-Modell
    )
    self.table_aris_arbeitsspeicher = "aris_arbeitsspeicher"
    self.table_principals = "principals"
    self.table_agent_reports = "agent_reports"

    # API-Key robust auflösen (Parameter -> Env -> Streamlit Secrets)
    self.api_key = self._resolve_api_key(api_key)

  def _resolve_api_key(self, passed_key: str = None) -> str:
    if passed_key:
      return passed_key

    for env_name in ["GROQ_API_KEY", "groq_api_key", "GROQ_KEY"]:
      val = os.getenv(env_name)
      if val:
        return val

    try:
      if hasattr(st, "secrets") and st.secrets:
        for key_name in ["GROQ_API_KEY", "groq_api_key", "GROQ_KEY"]:
          if key_name in st.secrets and st.secrets[key_name]:
            return st.secrets[key_name]
        for section in st.secrets:
          if isinstance(st.secrets[section], dict):
            for sub_key in ["groq_api_key", "GROQ_API_KEY", "api_key", "key"]:
              if sub_key in st.secrets[section] and st.secrets[section][sub_key]:
                return st.secrets[section][sub_key]
    except Exception:
      pass

    return None

  def analyze_and_optimize(self):
    print(
        f"Aris (Performance Manager [{self.model_name}]) analysiert den"
        " Arbeitsspeicher..."
    )
    try:
      # Optional: Wenn du den Groq-Client nutzen möchtest
      if not self.api_key:
        print("⚠️ Warnung: Kein Groq API-Key gefunden.")
      else:
        client = Groq(api_key=self.api_key)
        # Hier könntest du jetzt den Client für LLM-Calls nutzen, falls gewünscht

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

      df["high_adx"] = df["adx"] > 25 if "adx" in df.columns else False
      high_adx_count = int(df["high_adx"].sum())

      # --- KOMPAKTE BULLET-POINTS ---
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

      # 4. aris_arbeitsspeicher bereinigen
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