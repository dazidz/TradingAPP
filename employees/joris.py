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

  def run_synthesis(self, depot_focus: str, api_key: str):
    """Führt die tägliche Portfoliosynthese für das gewählte Mandat durch."""
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

      # 2. Depot-Daten abrufen (Beispiel-Tabelle, anpassen falls nötig)
      # depot_res = self.supabase.table("portfolios").select("*").eq("focus", depot_focus).execute()

      prompt = f"""
            Du bist Joris, der leitende Portfolio Manager. 
            Fokussand: {depot_focus}
            Analysiere die folgenden Team-Berichte und erstelle eine Synthese nach Ray Dalios Prinzipien (Radical Truth & Radical Open-Mindedness):
            
            {reports_text}
            """

      model = genai.GenerativeModel(model_name="gemini-1.5-flash")
      response = model.generate_content(prompt)
      report_content = response.text

      # 3. In Datenbank speichern
      self.supabase.table("agent_reports").insert({
          "agent_name": f"Joris_{depot_focus}",
          "report_content": report_content,
      }).execute()

      return True, "Synthese erfolgreich erstellt!"
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
          model_name="gemini-1.5-flash",
          system_instruction=(
              f"Du bist Joris, Portfolio Manager für das Depot-Mandat"
              f" '{depot_focus}'. Antworte direkt, ehrlich und datenbasiert"
              " nach Ray Dalio."
          ),
      )
      chat_session = model.start_chat(history=history)
      response = chat_session.send_message(user_message)
      return True, response.text
    except Exception as e:
      return False, f"Chat-Fehler: {e}"