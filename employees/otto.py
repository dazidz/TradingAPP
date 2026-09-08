from datetime import datetime
import google.generativeai as genai


class OttoAnalyst:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Otto"
    self.description = (
        "Pattern Matching & History Analyst (Historische Präzedenzfälle)"
    )

def run_analysis(self, api_key: str):  # api_key übergeben
  genai.configure(api_key=api_key)

    self.otto_dna = """
        Du bist Otto, der Analyst für historische Präzedenzfälle und Muster-Matching in unserem Team. 
        Deine Aufgabe ist es, aktuelle Marktsituationen, Signale oder makroökonomische Phasen mit historischen Ereignissen an den Finanzmärkten abzugleichen (z.B. Zinssenkungszyklen, Inflationsepisoden, Dotcom-Blase, 2018er QT-Schock, COVID-Crash etc.).
        
        Deine Aufgabe:
        1. Identifiziere historische Parallelen zur aktuellen Marktlage.
        2. Analysiere, wie Märkte damals reagiert haben und welche Sektoren gewannen oder verloren.
        3. Liefere prägnante, warnende oder bestätigende Muster-Erkenntnisse ("Das hatten wir schon mal..."). Keine Spekulation ins Blaue, sondern historische Evidenz.
        """

  def run_analysis(self):
    """Führt Ottos Muster-Analyse aus und speichert sie zentral in agent_reports."""
    try:

      # Optional: Wir können Janos letzten Makro-Bericht oder aktuelle Marktdaten einbinden, falls vorhanden
      jano_res = (
          self.supabase.table("agent_reports")
          .select("*")
          .eq("agent_name", "Jano")
          .order("created_at", desc=True)
          .limit(1)
          .execute()
      )
      jano_context = (
          jano_res.data[0]["report_content"]
          if jano_res.data
          else "Keine aktuellen Makro-Daten von Jano verfügbar."
      )

      context = f"""
            --- LETZTER MAKRO-KONTEXT (VON JANO) ---
            {jano_context}
            """

      model = genai.GenerativeModel(
          model_name="gemini-3.6-flash", system_instruction=self.otto_dna
      )
      response = model.generate_content(
          "Vergleiche die aktuelle Marktlage mit historischen Präzedenzfällen"
          f" und liefere dein Muster-Matching:\n\n{context}"
      )

      report_content = response.text
      today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

      # Zentral in agent_reports speichern
      self.supabase.table("agent_reports").insert({
          "agent_name": self.name,
          "report_content": f"**Report vom {today_str}:**\n\n{report_content}",
      }).execute()

      return (
          True,
          "Otto hat die historische Muster-Analyse erfolgreich abgeschlossen.",
      )
    except Exception as e:
      return False, f"Fehler bei Ottos Analyse: {e}"

  def get_latest_report(self):
    """Holt den neuesten Bericht von Otto aus der zentralen Tabelle."""
    try:
      res = (
          self.supabase.table("agent_reports")
          .select("*")
          .eq("agent_name", self.name)
          .order("created_at", desc=True)
          .limit(1)
          .execute()
      )
      return res.data[0] if res.data else None
    except Exception:
      return None