from datetime import datetime
import google.generativeai as genai
import pandas as pd


class JorisPortfolioManager:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Joris"
    self.description = (
        "Watchlist-Performance, Portfolio-Synthese & Teamroom-Schnittstelle"
    )

  def run_transfer_routine(self):
    """Führt Joris gesamte Hintergrund-Routine aus:

    1. Übertragung von max_performance_5_tage und setup_reason in den
    Arbeitsspeicher.
    2. Ermittlung und Speicherung der Top 5 & Flop 5 Performer der Watchlist.
    """
    self._process_performance_transfer()
    self.process_watchlist_performers()

  def _process_performance_transfer(self):
    """Interne Methode für den Transfer von Performance und setup_reason."""
    try:
      response = (
          self.supabase.table("joris_journal")
          .select("*")
          .not_.is_("max_performance_5_tage", "null")
          .execute()
      )
      records = response.data

      if not records:
        return

      for row in records:
        if not row.get("aris_übertrag", False):
          symbol = row.get("symbol", "N/A")
          max_perf = row.get("max_performance_5_tage")
          setup_reason = row.get("setup_reason", "Kein Grund angegeben")

          payload = {
              "kategorie": "performance_and_setup_transfer",
              "report_content": (
                  f"Transfer für Symbol {symbol}:\n"
                  f"- Max-Perf 5T: {max_perf}\n"
                  f"- Setup Reason: {setup_reason}"
              ),
              "created_at": datetime.now().isoformat(),
          }
          self.supabase.table("aris_arbeitsspeicher").insert(payload).execute()
          self.supabase.table("joris_journal").update(
              {"aris_übertrag": True}
          ).eq("id", row["id"]).execute()

    except Exception as e:
      print(f"Fehler beim Performance- und Setup-Transfer durch Joris: {e}")

  def process_watchlist_performers(self):
    """Ermittelt aus der Supabase-Tabelle 'watchlist' die Top 5 und Flop 5

    Performer und speichert diese im Arbeitsspeicher ab.
    """
    try:
      response = self.supabase.table("watchlist").select("*").execute()
      data = response.data

      if not data:
        return

      df = pd.DataFrame(data)
      perf_column = None
      for col in ["change_percent", "daily_change", "performance", "perf_1d"]:
        if col in df.columns:
          perf_column = col
          break

      if perf_column and not df.empty:
        df[perf_column] = pd.to_numeric(df[perf_column], errors="coerce")
        df = df.dropna(subset=[perf_column])

        df_sorted = df.sort_values(by=perf_column, ascending=False)
        top_5 = df_sorted.head(5)
        flop_5 = df_sorted.tail(5)

        today_str = datetime.now().strftime("%Y-%m-%d")
        symbol_col = "symbol" if "symbol" in df.columns else df.columns[0]

        payload = {
            "datum": today_str,
            "top_5": top_5[[symbol_col, perf_column]].to_dict(
                orient="records"
            ),
            "flop_5": flop_5[[symbol_col, perf_column]].to_dict(
                orient="records"
            ),
        }

        self.supabase.table("aris_arbeitsspeicher").insert({
            "kategorie": "watchlist_ranking",
            "report_content": (
                f"Watchlist Top/Flop Ranking vom {today_str}:\n{str(payload)}"
            ),
            "created_at": datetime.now().isoformat(),
        }).execute()

    except Exception as e:
      print(f"Fehler bei der Watchlist-Auswertung durch Joris: {e}")

  def run_synthesis(self, depot_focus, api_key):
    """Erstellt eine Portfolio-Synthese für das gewählte Mandat/Depot

    und speichert sie im Arbeitsspeicher.
    """
    if not api_key:
      return False, "Kein Gemini API-Key gefunden."

    try:
      genai.configure(api_key=api_key)
      model = genai.GenerativeModel("gemini-1.5-flash")

      # Daten laden (z.B. Watchlist oder Journal als Basis für die Synthese)
      response = self.supabase.table("watchlist").select("*").execute()
      data_context = str(response.data) if response.data else "Keine Daten"

      prompt = f"""
            Du bist Joris, der leitende Portfolio Manager. 
            Führe nach Ray Dalios Prinzipien ('Radical Truth & Radical Open-Mindedness') 
            eine Portfolio-Synthese für das Depot-Mandat '{depot_focus}' durch.
            
            Analysiere folgende Datenbasis und liefere eine präzise Empfehlung:
            {data_context}
            """

      result = model.generate_content(prompt)
      report_text = result.text

      # In den Arbeitsspeicher sichern
      payload = {
          "kategorie": f"synthesis_{depot_focus}",
          "report_content": report_text,
          "created_at": datetime.now().isoformat(),
      }
      self.supabase.table("aris_arbeitsspeicher").insert(payload).execute()

      return True, f"Synthese für '{depot_focus}' erfolgreich erstellt."
    except Exception as e:
      return False, f"Fehler bei der Synthese: {e}"

  def get_latest_report(self, depot_focus=None):
    """Ruft den neuesten Bericht für den gegebenen Depot-Fokus aus dem

    Arbeitsspeicher ab.
    """
    try:
      query = self.supabase.table("aris_arbeitsspeicher").select("*")
      if depot_focus:
        query = query.eq("kategorie", f"synthesis_{depot_focus}")

      res = query.order("created_at", desc=True).limit(1).execute()
      if res.data:
        return res.data[0]

      # Falls kein spezifischer gefunden wurde, den allerneuesten holen
      res_fallback = (
          self.supabase.table("aris_arbeitsspeicher")
          .select("*")
          .order("created_at", desc=True)
          .limit(1)
          .execute()
      )
      if res_fallback.data:
        return res_fallback.data[0]

      return None
    except Exception as e:
      print(f"Fehler beim Laden des neuesten Reports durch Joris: {e}")
      return None

  def chat_with_joris(
      self, depot_focus, user_message, chat_history, api_key
  ):
    """Führt einen interaktiven Chat mit Joris bezüglich des gewählten Depots."""
    if not api_key:
      return False, "Kein Gemini API-Key gefunden."

    try:
      genai.configure(api_key=api_key)
      model = genai.GenerativeModel("gemini-1.5-flash")

      system_instruction = (
          f"Du bist Joris, Portfolio Manager. Mandat: '{depot_focus}'. Handle"
          " nach Ray Dalios Prinzipien (Radical Truth & Radical"
          " Open-Mindedness)."
      )

      # Verlauf formatieren für Gemini
      formatted_history = []
      for msg in chat_history:
        role = "user" if msg["role"] == "user" else "model"
        formatted_history.append({"role": role, "parts": [msg["content"]]})

      chat = model.start_chat(history=formatted_history)
      response = chat.send_message(
          f"[{system_instruction}]\n\nFrage des Nutzers: {user_message}"
      )

      return True, response.text
    except Exception as e:
      return False, f"Fehler im Chat mit Joris: {e}"

  def get_aris_arbeitsspeicher_data(self):
    """Ruft die letzten Einträge aus dem Aris-Arbeitsspeicher ab."""
    try:
      res = (
          self.supabase.table("aris_arbeitsspeicher")
          .select("*")
          .order("created_at", desc=True)
          .limit(20)
          .execute()
      )
      return res.data
    except Exception as e:
      print(f"Fehler beim Laden des Arbeitsspeichers: {e}")
      return []