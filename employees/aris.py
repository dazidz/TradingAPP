from datetime import datetime
from db import get_db_client
from groq import Groq
import os
import streamlit as st


class ArisPerformanceManager:

  def __init__(self, supabase_client, api_key: str = None):
    self.supabase = supabase_client
    self.model_name = "openai/gpt-oss-120b"  # Alternativ: "llama-3.3-70b-versatile"
    self.table_aris_arbeitsspeicher = "aris_arbeitsspeicher"
    self.table_principals = "principals"
    self.table_agent_reports = "agent_reports"
    self.api_key = self._resolve_api_key(api_key)

  def _resolve_api_key(self, passed_key: str = None) -> str:
    if passed_key:
      return passed_key
      
    possible_keys = ["GROQ_API_KEY", "groq_api_key", "GROQ_KEY", "groq_key"]
    for env_name in possible_keys:
      val = os.getenv(env_name)
      if val:
        return val

    try:
      if hasattr(st, "secrets") and st.secrets:
        for key_name in possible_keys:
          if key_name in st.secrets and st.secrets[key_name]:
            return st.secrets[key_name]
        for section in st.secrets:
          sec_val = st.secrets[section]
          if isinstance(sec_val, dict):
            for sub_key in possible_keys + ["api_key", "key"]:
              if sub_key in sec_val and sec_val[sub_key]:
                return sec_val[sub_key]
    except Exception:
      pass
    return None

  def analyze_and_optimize(self):
    print(f"Aris (Performance & Synthese [{self.model_name}]) analysiert...")
    try:
      if not self.api_key:
        print("❌ Kein Groq API-Key gefunden.")
        return

      client = Groq(api_key=self.api_key)

      # 1. Alle Daten aus aris_arbeitsspeicher holen
      res = self.supabase.table(self.table_aris_arbeitsspeicher).select("*").execute()
      items = res.data or []

      if not items:
        print("Keine Einträge im aris_arbeitsspeicher gefunden.")
        return

      # 2. Alle Daten als Textzeilen aufbereiten
      formatted_lines = []
      for item in items:
        row_str = " | ".join([f"{k}: {v}" for k, v in item.items() if k != "id"])
        formatted_lines.append(f"- {row_str}")

      data_payload = "\n".join(formatted_lines)

      prompt = f"""
Du bist Aris, der Performance-Analyst. 
Dir liegen die von Nino vorbereiteten und berechneten Datensätze aus dem Arbeitsspeicher vor. 
Analysiere diese nach folgenden Kriterien:
- adx, smi Mustererkennung
- laufen 5 tage end oder max trades besser
- welche Signale laufen besser oder gibt es eine Signal adx, smi Kombi die gut läuft
- was gibt es bei den top 5 des tages für indikatoren
- prüft auf sonstige Muster (was funktioniert am besten)

Fasse diese in prägnante Bullet-Points zusammen.

VON NINO BEREITGESTELLTE DATEN:
{data_payload}
"""

      # 🔍 DEBUG: Prompt lokal als .txt-Datei speichern, um den Inhalt zu inspizieren
      debug_filename = "aris_prompt_debug.txt"
      try:
        with open(debug_filename, "w", encoding="utf-8") as f:
          f.write(prompt)
        print(f"📄 DEBUG: Prompt wurde erfolgreich in '{debug_filename}' geschrieben ({len(prompt)} Zeichen).")
      except Exception as write_err:
        print(f"⚠️ Konnte Debug-Datei nicht schreiben: {write_err}")

      # Zusätzliche Terminal-Statistiken
      print("=" * 60)
      print(f"📤 ARIS DEBUG: Anzahl Datensätze: {len(items)}")
      print(f"📤 ARIS DEBUG: Ungefähre Zeichen im Prompt: {len(prompt)}")
      print(f"📤 ARIS DEBUG: Ungefähre Token (Zeichen / 4): {len(prompt) // 4}")
      print("=" * 60)

      # 3. API-Aufruf über Groq
      completion = client.chat.completions.create(
          model=self.model_name,
          messages=[
              {"role": "system", "content": "Du bist ein präziser Analyst. Fasse dich klar, strukturiert und datenbasiert."},
              {"role": "user", "content": prompt}
          ],
          max_tokens=2000,
          temperature=0.1
      )

      llm_response = completion.choices[0].message.content
      print("✅ API-Aufruf von Aris erfolgreich durchgelaufen!")

      bullet_points = [
          f"Ausgewertete Datensätze von Nino: {len(items)}",
          "Qualitative KI-Synthese & Mustererkennung durchgeführt",
          llm_response[:300] + "...",
      ]

      # 4. In agent_reports speichern (für Joris)
      report_payload = {
          "agent_name": "Aris",
          "report_content": llm_response,
          "bullet_points": bullet_points,
          "status": "unread",
      }
      self.supabase.table(self.table_agent_reports).insert(
          report_payload
      ).execute()

      # 5. In principals speichern
      principal_entry = {
          "datum": datetime.now().strftime("%Y-%m-%d"),
          "manager": "Aris",
          "ki_modell": self.model_name,
          "erkenntnisse": llm_response,
          "status aktiv": True,
      }
      self.supabase.table(self.table_principals).insert(
          principal_entry
      ).execute()

      # 6. Arbeitsspeicher bereinigen
      item_ids = [item["id"] for item in items if "id" in item]
      for item_id in item_ids:
        self.supabase.table(self.table_aris_arbeitsspeicher).delete().eq(
            "id", item_id
        ).execute()

      print(
          "✅ Aris hat die Nino-Daten via Groq verarbeitet, Report abgelegt und Arbeitsspeicher bereinigt."
      )

    except Exception as e:
      print(f"❌ FEHLER-DETAILS IN ARIS (Groq/API-Limit): {e}")

  def run_all(self):
    self.analyze_and_optimize()


if __name__ == "__main__":
  supabase_client = get_db_client()
  aris = ArisPerformanceManager(supabase_client)
  aris.run_all()