from datetime import datetime
import json
import os
import re
import google.generativeai as genai
import pandas as pd
import streamlit as st


class JorisPortfolioManager:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Joris"
    self.model_name = "gemini-3.6-flash"
    self.description = (
        "Portfolio Manager & Synthese-Agent nach Ray Dalios Prinzipien."
    )

  def _get_table_name(self, depot_focus: str) -> str:
    mapping = {
        "invest": "invest_depot",
        "swing": "swing_depot",
        "high_risk": "risk_depot",
    }
    return mapping.get(depot_focus, "invest_depot")

  def _resolve_api_key(self, passed_key: str = None) -> str:
    """Ultimative Schlüsselsuche: Prüft Parameter, Env, alle denkbaren Secret-Namen."""
    if passed_key:
      return passed_key

    # 1. Bekannte Env-Variablen prüfen
    for env_name in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY"]:
      val = os.getenv(env_name)
      if val:
        return val

    # 2. Streamlit Secrets durchkämmen
    try:
      if hasattr(st, "secrets") and st.secrets:
        # Direkte Treffer
        for key_name in [
            "GEMINI_API_KEY",
            "gemini_api_key",
            "GOOGLE_API_KEY",
            "google_api_key",
            "GEMINI_KEY",
        ]:
          if key_name in st.secrets and st.secrets[key_name]:
            return st.secrets[key_name]

        # Verschachtelte Bereiche prüfen (z.B. [api_keys] gemini = "...")
        for section in st.secrets:
          if isinstance(st.secrets[section], dict):
            for sub_key in ["gemini_api_key", "GEMINI_API_KEY", "api_key", "key"]:
              if sub_key in st.secrets[section] and st.secrets[section][sub_key]:
                return st.secrets[section][sub_key]
    except Exception:
      pass

    return None

  def run_synthesis(self, depot_focus: str, api_key: str = None):
    try:
      active_key = self._resolve_api_key(api_key)

      if not active_key:
        return (
            False,
            "Kein Gemini API-Key für Joris gefunden (weder übergeben, noch in"
            " Env oder Streamlit Secrets vorhanden).",
        )

      genai.configure(api_key=active_key)
      model = genai.GenerativeModel(self.model_name)

      # 1. NUR UNGELESENE BERICHTE DER KOLLEGEN ABRUFEN (Status = 'unread')
      reports_res = (
          self.supabase.table("agent_reports")
          .select("id, created_at, agent_name, bullet_points, report_content")
          .eq("status", "unread")
          .order("created_at", desc=True)
          .execute()
      )

      raw_reports = reports_res.data if reports_res.data else []

      formatted_reports_list = []
      processed_report_ids = []

      for rep in raw_reports:
        agent = rep.get("agent_name", "Unbekannt")
        # Joris liest nicht seine eigenen Berichte
        if "Joris" in agent:
          continue

        processed_report_ids.append(rep.get("id"))
        bullets = rep.get("bullet_points")

        if bullets:
          formatted_reports_list.append(
              f"--- Agent: {agent} (vom {rep.get('created_at')}) ---\n"
              + "\n".join([f"- {b}" for b in bullets])
          )
        else:
          content = rep.get("report_content", "")
          formatted_reports_list.append(
              f"--- Agent: {agent} ---\n{content[:300]}"
          )

      reports_text = (
          "\n\n".join(formatted_reports_list)
          if formatted_reports_list
          else "Keine neuen Team-Bullet-Points vorhanden."
      )

      # 2. Depot, Signale und Favoriten laden
      table_name = self._get_table_name(depot_focus)
      depot_res = self.supabase.table(table_name).select("*").execute()
      depot_data_text = (
          str(depot_res.data) if depot_res.data else "Keine Einträge."
      )

      screener_res = (
          self.supabase.table("signals").select("*").limit(20).execute()
      )
      screener_data_text = (
          str(screener_res.data) if screener_res.data else "Keine Signale."
      )

      favorites_res = self.supabase.table("favorites").select("*").execute()
      favorites_data_text = (
          str(favorites_res.data) if favorites_res.data else "Keine Favoriten."
      )

      # Prompt zusammenbauen
      prompt_content = f"""
            Du bist Joris, der leitende Portfolio Manager. 
            Deine Arbeitsweise folgt Ray Dalios Prinzipien: **Radical Truth & Radical Open-Mindedness**.
            Fokus-Mandat: {depot_focus.upper()} (Zugehörige Depot-Tabelle: {table_name})
            
            WICHTIG - TRADINGVIEW LINKS:
            Füge bei **jeder** erwähnten Aktie im Markdown-Format einen Link ein: `[Ticker](https://www.tradingview.com/chart/?symbol=NASDAQ:TICKER)`.

            DATENGRUNDLAGE (Nur frische Team-Bullet-Points):
            A) DEPOT ({table_name}): {depot_data_text}
            B) SCREENER: {screener_data_text}
            C) FAVORITEN: {favorites_data_text}
            D) NEUESTE TEAM-BULLET-POINTS: {reports_text}
            
            AUFGABE:
            Erstelle eine datenbasierte Portfolio-Synthese für '{depot_focus.upper()}'. 
            1. Zusammenfassung & Synthese der Bullet-Points.
            2. Depot-Prüfung & Diversifikation.
            3. Verkaufsempfehlungen.
            4. Top-Empfehlungen des Tages.
            
            ZUSATZ-FORMAT FÜR DAS JOURNAL (BEI SWING):
            ===JOURNAL_DATA_START===
            [
              {{"ticker": "AAPL", "setup_reason": "Ausbruch", "target": 220.0, "stop_loss": 175.0}}
            ]
            ===JOURNAL_DATA_END===
            """

      response = model.generate_content(prompt_content)
      report_content = response.text

      # 3. Bericht in agent_reports speichern (mit status 'unread' für den Chef)
      self.supabase.table("agent_reports").insert({
          "agent_name": f"Joris_{depot_focus}",
          "report_content": report_content,
          "bullet_points": [
              f"Synthese Mandat {depot_focus.upper()} erfolgreich abgeschlossen",
              "Frische Team-Daten und Screener-Signale verarbeitet",
          ],
          "status": "unread",
          "created_at": datetime.now().isoformat(),
      }).execute()

      # 4. WICHTIG: Die verarbeiteten Team-Berichte jetzt auf 'processed' setzen
      for rep_id in processed_report_ids:
        self.supabase.table("agent_reports").update({"status": "processed"}).eq(
            "id", rep_id
        ).execute()

      # 5. Journal befüllen bei Swing
      if depot_focus.lower() == "swing":
        match = re.search(
            r"===JOURNAL_DATA_START===\s*(.*?)\s*===JOURNAL_DATA_END===",
            report_content,
            re.DOTALL,
        )
        if match:
          picks = json.loads(match.group(1))
          for pick in picks:
            self.supabase.table("joris_journal").insert({
                "ticker": pick.get("ticker", "UNKNOWN"),
                "setup_reason": pick.get("setup_reason", ""),
                "target": float(pick.get("target", 0.0)),
                "stop_loss": float(pick.get("stop_loss", 0.0)),
                "status": "active",
                "created_at": datetime.now().isoformat(),
            }).execute()

      return True, f"Synthese für '{table_name}' erfolgreich erstellt!"
    except Exception as e:
      return False, f"Fehler bei der Synthese: {e}"

  def get_latest_report(self, depot_focus: str):
    try:
      agent_name = f"Joris_{depot_focus}"
      res = (
          self.supabase.table("agent_reports")
          .select("*")
          .eq("agent_name", agent_name)
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
      api_key: str = None,
  ):
    try:
      active_key = self._resolve_api_key(api_key)
      if not active_key:
        return False, "Kein Gemini API-Key für den Joris-Chat gefunden."

      genai.configure(api_key=active_key)
      model = genai.GenerativeModel(self.model_name)

      formatted_history = []
      for msg in chat_history:
        role = "user" if msg["role"] == "user" else "model"
        formatted_history.append({"role": role, "parts": [msg["content"]]})

      chat = model.start_chat(history=formatted_history)

      system_context = f"""
            Du bist Joris, der leitende Portfolio Manager. Du chattest mit deinem Vorgesetzten.
            Aktuelles Fokus-Mandat: {depot_focus.upper()}.
            Handle stets nach Ray Dalios Prinzipien: Radical Truth & Radical Open-Mindedness.
            Antworte präzise, analytisch und direkt auf Basis der vorliegenden Mandatsdaten.
            """

      full_prompt = f"{system_context}\n\nFrage des Nutzers: {user_message}"
      response = chat.send_message(full_prompt)
      return True, response.text
    except Exception as e:
      return False, f"Fehler im Chat mit Joris: {e}"