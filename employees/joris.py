from datetime import datetime
import google.generativeai as genai
import pandas as pd


class JorisPortfolioManager:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Joris"
    self.description = (
        "Lead Portfolio Manager (Synthese & Depot-Überwachung nach Ray Dalio)"
    )

    self.joris_dna = """
        Du bist Joris, der leitende Portfolio Manager in unserem Team. Du steuerst das Team nach Ray Dalios Prinzipien: 
        Radical Truth & Radical Open-Mindedness. Deine Aufgaben sind:
        1. Die Berichte der Spezialisten zu einer kohärenten Synthese für das gewählte Mandat zu verdichten.
        2. Das entsprechende Depot des Nutzers (Invest-, Swing- oder Risk-Depot) kritisch auf Diversifikation, Klumpenrisiken und Rebalancing-Bedarf zu prüfen.
        3. Konkrete KAUF- und VERKAUFSEMPFEHLUNGEN auszusprechen – basierend auf den harten technischen Signalen (inkl. der bereitgestellten TradingView-Links) und den Fundamentaldaten.
        
        WICHTIG - MANDATS- UND SIGNAL-DISZIPLIN:
        Bei Mandaten wie 'Swing', 'Invest' oder 'High Risk' darfst du NUR Titel berücksichtigen, die nachweislich ein aktives technisches Signal in unserer Signalliste haben.
        """

  def _get_active_signals(self, depot_focus: str):
    """Holt aktive Signale inklusive TradingView/Gettex-Daten aus der signals-Tabelle."""
    try:
      focus_lower = depot_focus.lower()
      if "risk" in focus_lower or "high" in focus_lower:
        strategy_target = "High Risk"
      else:
        strategy_target = "Swing"

      res = (
          self.supabase.table("signals")
          .select(
              "ticker, company_name, signal_type, entry_price, created_at,"
              " strategy_type, gettex_ticker, meta_data"
          )
          .ilike("strategy_type", f"%{strategy_target}%")
          .execute()
      )

      if not res.data:
        return []

      # TradingView-Link direkt für jede Zeile generieren
      signals_processed = []
      for row in res.data:
        t = row.get("ticker")
        gettex = row.get("gettex_ticker")
        tv_symbol = gettex if gettex else t
        tv_link = f"https://www.tradingview.com/chart/?symbol={tv_symbol}"

        row_copy = row.copy()
        row_copy["TradingView"] = tv_link
        signals_processed.append(row_copy)

      return signals_processed
    except Exception as e:
      print(f"Fehler beim Abrufen der Signale: {e}")
      return []

  def _get_current_portfolio(self, depot_focus: str):
    """Holt das zugehörige Depot (invest_depot, swing_depot oder risk_depot) aus Supabase."""
    try:
      focus_lower = depot_focus.lower()

      if "invest" in focus_lower:
        table_name = "invest_depot"
      elif "risk" in focus_lower or "high" in focus_lower:
        table_name = "risk_depot"
      else:
        table_name = "swing_depot"

      res = self.supabase.table(table_name).select("*").execute()
      return (
          res.data
          if res.data
          else f"Kein Bestand in `{table_name}` hinterlegt."
      )
    except Exception as e:
      return f"Depot konnte nicht geladen werden ({e})."

  def run_synthesis(self, depot_focus: str, api_key: str):
    """Führt die Portfolio-Synthese und den Depot-Check für das gewählte Mandat aus."""
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
            --- AKTIVE TECHNISCHE SIGNALE & TRADINGVIEW-LINKS (PFLICHT-FILTER) ---
            {signal_df.to_string(index=False)}
            """

      # 2. Das passende Depot laden
      current_portfolio = self._get_current_portfolio(depot_focus)
      portfolio_context = f"""
            --- AKTUELLES DEPOT ({depot_focus}) & BESTÄNDE ---
            {current_portfolio}
            """

      # 3. Spezialisten-Berichte einsammeln
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

      context = f"""
            --- GEWÄHLTES MANDAT / DEPOT-FOKUS ---
            {depot_focus}

            {signal_context}

            {portfolio_context}

            --- JANO (MAKRO-BERICHT) ---
            {get_report('Jano')}

            --- PETER (MICRO & INSIDER-BERICHT) ---
            {get_report('Peter')}

            --- OTTO (HISTORISCHER MISTER-BERICHT) ---
            {get_report('Otto')}
            """

      model = genai.GenerativeModel(
          model_name="gemini-3.6-flash", system_instruction=self.joris_dna
      )
      response = model.generate_content(
          "Erstelle eine Portfolio-Synthese für das Mandat"
          f" '{depot_focus}'. Prüfe das aktuelle Depot auf Diversifikation,"
          " sprich konkrete KAUF- und VERKAUFSEMPFEHLUNGEN aus und binde die"
          " TradingView-Links aus der Signalliste direkt als Markdown-Links bei"
          f" den jeweiligen Aktien ein:\n\n{context}"
      )

      report_content = response.text
      today_str = datetime.now().strftime("%Y-%m-%d %H:%M")

      self.supabase.table("agent_reports").insert({
          "agent_name": f"Joris_{depot_focus}",
          "report_content": (
              f"**Portfolio-Synthese & Depot-Check ({depot_focus}) vom"
              f" {today_str}:**\n\n{report_content}"
          ),
      }).execute()

      return (
          True,
          f"Joris hat die Synthese und den Depot-Check für '{depot_focus}'"
          " erfolgreich abgeschlossen.",
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