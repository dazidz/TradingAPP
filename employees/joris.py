from datetime import datetime
import google.generativeai as genai
import pandas as pd


class JorisPortfolioManager:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Joris"
    self.description = (
        "Portfolio Manager & Synthese-Agent nach Ray Dalios Prinzipien."
    )

  def _get_table_name(self, depot_focus: str) -> str:
    """Mappt den Depot-Fokus auf den echten Tabellennamen in Supabase."""
    mapping = {
        "invest": "invest_depot",
        "swing": "swing_depot",
        "high_risk": "risk_depot",
    }
    return mapping.get(depot_focus, "invest_depot")

  def run_synthesis(self, depot_focus: str, api_key: str):
    """Führt die tägliche Portfoliosynthese durch:

    - Führt Berichte der anderen Agenten zusammen
    - Prüft das gewählte Depot (invest_depot, swing_depot, risk_depot)
    - Lädt die aktuellen Signale direkt aus der Screener-Tabelle
    - Gibt konkrete Empfehlungen zu Verkauf, Diversifikation und Top-T Picks ab.
    """
    try:
      genai.configure(api_key=api_key)

      # 1. Berichte der anderen Agenten abrufen (Jano, Peter, Otto, Aris etc.)
      reports_res = (
          self.supabase.table("agent_reports")
          .select("*")
          .order("created_at", desc=True)
          .limit(10)
          .execute()
      )
      reports_text = (
          str(reports_res.data) if reports_res.data else "Keine Berichte."
      )

      # 2. Das passende Depot dynamisch abrufen
      table_name = self._get_table_name(depot_focus)
      try:
        depot_res = self.supabase.table(table_name).select("*").execute()
        depot_data_text = (
            str(depot_res.data)
            if depot_res.data
            else f"Keine Einträge in Tabelle '{table_name}' gefunden."
        )
      except Exception as db_err:
        depot_data_text = (
            f"Konnte Tabelle '{table_name}' nicht abrufen: {db_err}"
        )

      # 3. SIGNALE DIREKT AUS DER SCREENER-TABELLE ABRUFEN

      screener_table_name = (
          "signals"  # z.B. "screener_signals"
      )
      try:
        screener_res = (
            self.supabase.table(screener_table_name)
            .select("*")
            .limit(20)
            .execute()
        )
        screener_data_text = (
            str(screener_res.data)
            if screener_res.data
            else f"Keine Einträge in Screener-Tabelle '{screener_table_name}'"
            " gefunden."
        )
      except Exception as screener_err:
        screener_data_text = (
            f"Konnte Screener-Tabelle '{screener_table_name}' nicht abrufen"
            f" (Bitte Tabellennamen anpassen): {screener_err}"
        )

      # 4. Präziser Prompt, der alle geforderten Punkte explizit abfragt
      prompt = f"""
            Du bist Joris, der leitende Portfolio Manager. 
            Deine Arbeitsweise folgt Ray Dalios Prinzipien: **Radical Truth & Radical Open-Mindedness**.
            Fokus-Mandat: {depot_focus.upper()} (Zugehörige Depot-Tabelle: {table_name})
            
            DIR LIEGEN FOLGENDE DATEN VOR:
            
            A) AKTUELLER BESTAND DES GEWÄHLTEN DEPOTS ({table_name}):
            {depot_data_text}
            
            B) AKTUELLE SIGNALE AUS DEM SCREENER ({screener_table_name}):
            {screener_data_text}
            
            C) LETZTE BERICHTE DER TEAM-KOLLEGEN (Makro, Insider, History, Performance):
            {reports_text}
            
            DEINE AUFGABE:
            Erstelle eine kompromisslose, datenbasierte Portfolio-Synthese. Gehe dabei strikt auf folgende Punkte ein:
            1. **Zusammenfassung & Synthese:** Führe die Erkenntnisse der anderen Kollegen im Kontext des aktuellen Marktumfelds zusammen.
            2. **Depot-Prüfung & Diversifikation:** Analysiere das aktuelle Depot ({table_name}). Gibt es Klumpenrisiken, fehlende Diversifikation oder Positionen, die angepasst werden müssen?
            3. **Verkaufsempfehlungen:** Benenne glasklar, welche Positionen im Depot reduziert oder komplett abgestoßen werden sollten (Loss Cutting / Gewinnmitnahme).
            4. **Top-Empfehlungen des Tages:** Gleiche die Depot-Ziele mit den aktuellen Signalen aus dem Screener ab und präsentiere die besten High-Conviction-Kandidaten für dieses Mandat.
            """

      model = genai.GenerativeModel(model_name="gemini-3.6-flash")
      response = model.generate_content(prompt)
      report_content = response.text

      # 5. In Datenbank speichern
      self.supabase.table("agent_reports").insert({
          "agent_name": f"Joris_{depot_focus}",
          "report_content": report_content,
      }).execute()

      return (
          True,
          f"Synthese inklusive Depot- und Screener-Auswertung für '{table_name}'"
          " erfolgreich erstellt!",
      )
    except Exception as e:
      return False, f"Fehler bei der Synthese: {e}"

  def get_latest_report(self, depot_focus: str):
    """Holt den neuesten Joris-Bericht für das Depot."""
    try:
      res = (
          self.supabase.table("agent_reports")
          .select("*")
          .eq("agent_name", f"Joris_{depot_focus}")
          .order("created_at", desc=True)
          .limit(1)
          .execute()
      )
      return res.data[0] if res.data else None
    except Exception:
      return None

  def chat_with_joris(
      self,
      depot_focus: str,
      user_message: str,
      chat_history: list,
      api_key: str,
  ):
    """Ermöglicht den Chat mit Joris im Teamroom."""
    try:
      genai.configure(api_key=api_key)

      history = []
      for m in chat_history:
        role = "user" if m["role"] == "user" else "model"
        if not history and role == "model":
          continue
        history.append({"role": role, "parts": [m["content"]]})

      model = genai.GenerativeModel(
          model_name="gemini-3.6-flash",
          system_instruction=(
              f"Du bist Joris, Portfolio Manager für das Depot-Mandat"
              f" '{depot_focus}'. Du hast Zugriff auf das Depot, den Screener"
              " und die Team-Berichte. Antworte direkt, ehrlich und"
              " datenbasiert nach Ray Dalio."
          ),
      )
      chat_session = model.start_chat(history=history)
      response = chat_session.send_message(user_message)
      return True, response.text
    except Exception as e:
      return False, f"Chat-Fehler: {e}"