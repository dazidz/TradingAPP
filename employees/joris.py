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
    # Fallback auf 'invest_depot', falls ein unbekannter Fokus kommt
    return mapping.get(depot_focus, "invest_depot")

  def run_synthesis(self, depot_focus: str, api_key: str):
    """Führt die tägliche Portfoliosynthese für das gewählte Mandat durch

    und bindet die echten Depot-Daten aus der jeweiligen Tabelle ein.
    """
    try:
      genai.configure(api_key=api_key)

      # 1. Berichte der anderen Agenten abrufen
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

      # 2. RICHTIGE DEPOT-TABELLE DYNAMISCH ABRUFEN
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

      # 3. Prompt zusammenbauen
      prompt = f"""
            Du bist Joris, der leitende Portfolio Manager. 
            Fokus-Mandat: {depot_focus} (Datenbank-Tabelle: {table_name})
            
            HIER SIND DIE AKTUELLEN BESTÄNDE AUS DEM DEPOT ({table_name}):
            {depot_data_text}
            
            HIER SIND DIE LETZTEN TEAM-BERICHTE (Makro, Insider, History, etc.):
            {reports_text}
            
            Analysiere die aktuellen Depot-Bestände im Kontext der Team-Berichte und erstelle eine Synthese sowie klare Handlungsanweisungen nach Ray Dalios Prinzipien (Radical Truth & Radical Open-Mindedness).
            """

      model = genai.GenerativeModel(model_name="gemini-2.5-flash")
      response = model.generate_content(prompt)
      report_content = response.text

      # 4. In Datenbank speichern
      self.supabase.table("agent_reports").insert({
          "agent_name": f"Joris_{depot_focus}",
          "report_content": report_content,
      }).execute()

      return True, f"Synthese für '{table_name}' erfolgreich erstellt!"
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
          model_name="gemini-2.5-flash",
          system_instruction=(
              f"Du bist Joris, Portfolio Manager für das Depot-Mandat"
              f" '{depot_focus}'. Du hast Zugriff auf die Bestände und"
              " Team-Berichte. Antworte direkt, ehrlich und datenbasiert nach"
              " Ray Dalio."
          ),
      )
      chat_session = model.start_chat(history=history)
      response = chat_session.send_message(user_message)
      return True, response.text
    except Exception as e:
      return False, f"Chat-Fehler: {e}"