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
        Radical Truth & Radical Open-Mindedness. Deine Aufgabe ist es, die Berichte der Spezialisten kritisch zu hinterfragen und zu einer fundierten, kohärenten Portfolio-Synthese für das gewählte Mandat zu verdichten.
        
        WICHTIG - MANDATS- UND SIGNAL-DISZIPLIN:
        1. Bei Mandaten wie 'Swing', 'Invest' oder 'High Risk' darfst du NUR Titel berücksichtigen, die nachweislich ein aktives technisches Signal in unserer Signalliste haben. Werte ohne technisches Signal fliegen rigoros raus!
        Formuliere klare, kompromisslose Handlungsempfehlungen und Risikohinweise.
        """

  def _get_active_signals(self, depot_focus: str):
    """Holt aktive Signale aus der signals-Tabelle basierend auf dem strategy_type:

    - Swing & Invest -> sucht nach 'Swing'
    - High Risk -> sucht nach 'High Risk'
    """
    try:
      focus_lower = depot_focus.lower()

      # Mandats-Logik nach Vorgabe mappen
      if "risk" in focus_lower or "high" in focus_lower:
        strategy_target = "High Risk"
      else:
        # Gilt für 'Swing' und 'Invest' (Invest greift auf Swing-Signale zu)
        strategy_target = "Swing"

      res = (
          self.supabase.table("signals")
          .select(
              "ticker, company_name, signal_type, entry_price, created_at,"
              " strategy_type, meta_data"
          )
          .ilike("strategy_type", f"%{strategy_target}%")
          .execute()
      )
      return res.data if res.data else []
    except Exception as e:
      print(f"Fehler beim Abrufen der Signale: {e}")
      return []

  def run_synthesis(self, depot_focus: str, api_key: str):
    """Führt die Portfolio-Synthese für das gewählte Mandat aus (mit striktem Signal-Filter)."""
    try:
      genai.configure(api_key=api_key)

      # 1. Signale für das Mandat abrufen
      active_signals = self._get_active_signals(depot_focus)

      if not active_signals or len(active_signals) == 0:
        focus_label = (
            "High Risk"
            if "risk" in depot_focus.lower() or "high" in depot_focus.lower()
            else "Swing"
        )
        return (
            False,
            f"Stopp: Für das Mandat '{depot_focus}' wurden keine aktiven"
            f" Einträge (strategy_type: '{focus_label}') in der `signals`-Tabelle"
            " gefunden. Keine Synthese möglich.",
        )

      signal_df = pd.DataFrame(active_signals)
      signal_context = f"""
            --- AKTIVE TECHNISCHE SIGNALE (PFLICHT-FILTER FÜR DIESES MANDAT) ---
            NUR DIE FOLGENDEN TICKER DÜRFEN GEHANDELT/EMPFOHLEN WERDEN:
            {signal_df.to_string(index=False)}
            """

      # 2. Die neuesten Reports der anderen Agenten einsammeln
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

            {signal_context}

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
          "Erstelle auf Basis der Team-Berichte und der strikten"
          " Signal-Disziplin eine fundierte Portfolio-Synthese für das Mandat"
          f" '{depot_focus}':\n\n{context}"
      )

      report_content = response.text
      today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

      self.supabase.table("agent_reports").insert({
          "agent_name": f"Joris_{depot_focus}",
          "report_content": (
              f"**Portfolio-Synthese ({depot_focus}) vom {today_str}:**\n\n"
              f"{report_content}"
          ),
      }).execute()

      return (
          True,
          f"Joris hat die Portfolio-Synthese für '{depot_focus}' unter"
          " Berücksichtigung der Signale erfolgreich abgeschlossen.",
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