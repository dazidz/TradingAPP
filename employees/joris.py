from datetime import datetime
import google.generativeai as genai
import pandas as pd


class JorisPortfolioManager:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Joris"
    self.description = (
        "Portfolio Manager (Synthese & Mandats-Regelwerk für Invest, Swing,"
        " High Risk)"
    )

    self.joris_dna = """
        Du bist Joris, der leitende Portfolio Manager in unserem Team. Deine Aufgabe ist es, die Analysen aller Teammitglieder (Jano für Makro, Peter für Micro/Insider, Otto für Historie, Nino für Signale und Aris für Performance) zu synthetisieren.
        Du arbeitest strikt nach drei unterschiedlichen Mandaten:
        1. **Invest (Langfristiges Fundament / Core):** Fokus auf Jano + Peter. Keine Hektik, breite Streuung, niedrige Umschlagshäufigkeit, keine Derivate.
        2. **Swing (Mittelfristige Trendfolge):** Fokus auf Aris + Otto + Peter (Sektor-Momentum). Klare Ein- und Ausstiegspunkte, striktes Risikomanagement.
        3. **High Risk (Spekulation / Alpha-Jagd):** Aggressive Einzelwerte, Earnings-Plays. Maximales Budget-Cap von 10%. Wenn Gewinne entstehen, MUSS rebalanciert werden.

        Deine Aufgabe:
        Nimm die Berichte der anderen Agenten und den aktuellen Depot-Status, prüfe die Risikoparameter und sprich eine konkrete, mandatsbezogene Empfehlung aus.
        """

  def run_synthesis(self, depot_focus="invest"):
    """Führt die Portfoliowerdung und Mandats-Prüfung durch."""
    try:
      import streamlit as st

      api_key = st.secrets["GEMINI_API_KEY"]
      genai.configure(api_key=api_key)

      # Neueste Berichte aller Agenten aus der zentralen Tabelle holen
      agents = ["Jano", "Peter", "Otto", "Aris"]
      team_context = ""
      for agent in agents:
        res = (
            self.supabase.table("agent_reports")
            .select("*")
            .eq("agent_name", agent)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
          team_context += (
              f"\n--- {agent.upper()} REPORT ---\n"
              f"{res.data[0]['report_content']}\n"
          )

      # Aktuelle Positionen des gewählten Depots aus Supabase holen
      depot_res = (
          self.supabase.table("trade_journal")
          .select("*")
          .eq("depot_type", depot_focus)
          .execute()
      )
      depot_df = pd.DataFrame(depot_res.data)

      context = f"""
            GEWÄHLTES MANDAT / DEPOT: {depot_focus.upper()}
            
            --- AKTUELLE POSITIONEN IM DEPOT ---
            {depot_df.to_string() if not depot_df.empty else "Keine offenen Positionen in diesem Depot."}
            
            --- TEAM BERICHTE ---
            {team_context if team_context else "Keine Team-Berichte gefunden."}
            """

      model = genai.GenerativeModel(
          model_name="gemini-3.6-flash", system_instruction=self.joris_dna
      )
      response = model.generate_content(
          f"Erstelle deine Portfolio-Synthese und Handlungsempfehlung speziell"
          f" für das Mandat '{depot_focus}':\n\n{context}"
      )

      report_content = response.text
      today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

      # Zentral in agent_reports speichern (mit Hinweis auf das Depot)
      self.supabase.table("agent_reports").insert({
          "agent_name": f"{self.name} ({depot_focus.upper()})",
          "report_content": f"**Portfolio-Synthese für {depot_focus.upper()} vom {today_str}:**\n\n{report_content}",
      }).execute()

      return (
          True,
          f"Joris hat die Synthese für das Mandat '{depot_focus}' erfolgreich"
          " abgeschlossen.",
      )
    except Exception as e:
      return False, f"Fehler bei Joris Synthese: {e}"

  def get_latest_report(self, depot_focus="invest"):
    """Holt den neuesten Joris-Bericht für das spezifische Mandat."""
    try:
      target_name = f"{self.name} ({depot_focus.upper()})"
      res = (
          self.supabase.table("agent_reports")
          .select("*")
          .eq("agent_name", target_name)
          .order("created_at", desc=True)
          .limit(1)
          .execute()
      )
      return res.data[0] if res.data else None
    except Exception:
      return None