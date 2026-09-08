from datetime import datetime
import google.generativeai as genai
import pandas as pd


class JorisPortfolioManager:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Joris"
    self.description = (
        "Lead Portfolio Manager (Synthese nach Ray Dalios Prinzipien)"
    )

    self.joris_dna = """
        Du bist Joris, der leitende Portfolio Manager in unserem Team. Du steuerst das Team nach Ray Dalios Prinzipien: 
        Radical Truth & Radical Open-Mindedness. Deine Aufgabe ist es, die Berichte der Spezialisten (Jano für Makro, Peter für Micro/Insider, Otto für Historie/Muster) zu nehmen, kritisch zu hinterfragen und zu einer fundierten, kohärenten Portfolio-Synthese für das gewählte Mandat zu verdichten.
        
        Deine Aufgabe:
        1. Führe die Erkenntnisse der anderen Agenten zusammen.
        2. Setze sie in direkten Bezug zum gewählten Depot-Fokus (Invest, Swing oder High Risk).
        3. Formuliere klare, kompromisslose Handlungsempfehlungen und Risikohinweise.
        """

  def run_synthesis(self, depot_focus: str, api_key: str):
    """Führt die Portfolio-Synthese für das gewählte Mandat aus und speichert sie."""
    try:
      genai.configure(api_key=api_key)

      # Die neuesten Reports der anderen Agenten einsammeln
      def get_report(agent_name):
        try:
          res = (
              self.supabase.table("agent_reports")
              .select("report_content")
              .eq("agent_name", agent_name)
              .order("created_at", desc=True)
              .limit(1)
              .execute()
          )
          return (
              res.data[0]["report_content"]
              if res.data
              else "Kein Bericht verfügbar."
          )
        except Exception:
          return "Fehler beim Laden."

      jano_report = get_report("Jano")
      peter_report = get_report("Peter")
      otto_report = get_report("Otto")

      context = f"""
            --- GEWÄHLTES MANDAT / DEPOT-FOKUS ---
            {depot_focus}

            --- JANO (MAKRO-BERICHT) ---
            {jano_report}

            --- PETER (MICRO & INSIDER-BERICHT) ---
            {peter_report}

            --- OTTO (HISTORISCHER MISTER-BERICHT) ---
            {otto_report}
            """

      model = genai.GenerativeModel(
          model_name="gemini-3.6-flash", system_instruction=self.joris_dna
      )
      response = model.generate_content(
          "Erstelle auf Basis der Team-Berichte eine fundierte"
          f" Portfolio-Synthese für das Mandat '{depot_focus}':\n\n{context}"
      )

      report_content = response.text
      today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

      # In agent_reports mit speziellem Mandatsbezug speichern
      self.supabase.table("agent_reports").insert({
          "agent_name": f"Joris_{depot_focus}",
          "report_content": (
              f"**Portfolio-Synthese ({depot_focus}) vom {today_str}:**\n\n"
              f"{report_content}"
          ),
      }).execute()

      return (
          True,
          f"Joris hat die Portfolio-Synthese für '{depot_focus}' abgeschlossen.",
      )
    except Exception as e:
      return False, f"Fehler bei Joris Synthese: {e}"

  def get_latest_report(self, depot_focus: str):
    """Holt den neuesten Joris-Bericht für das spezifische Mandat."""
    try:
      agent_key = f"Joris_{depot_focus}"
      res = (
          self.supabase.table("agent_reports")
          .select("*")
          .eq("agent_name", agent_key)
          .order("created_at", desc=True)
          .limit(1)
          .execute()
      )
      return res.data[0] if res.data else None
    except Exception:
      return None