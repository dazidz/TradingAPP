from datetime import datetime
import json
import os
import re
from groq import Groq
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
    """Führt die tägliche Portfoliosynthese durch via Groq (Llama 3.3 70B):

    - Führt Berichte der anderen Agenten zusammen
    - Prüft das gewählte Depot (invest_depot, swing_depot, risk_depot)
    - Lädt die aktuellen Signale aus der 'signals'-Tabelle
    - Lädt die favorisierten Werte aus der 'favorites'-Tabelle
    - Wendet die mandatspezifische Brille an (Fundamental vs. Technische Indikatoren)
    - Gibt konkrete Empfehlungen mit direkten TradingView-Links ab.
    """
    try:
      # Groq Client initialisieren (nutzt den übergebenen Key oder Fallback auf Environment)
      active_key = api_key if api_key else os.getenv("GROQ_API_KEY")
      groq_client = Groq(api_key=active_key)

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

      # 3. SIGNALE AUS DER 'signals'-TABELLE ABRUFEN
      screener_table_name = "signals"
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
            else f"Keine Einträge in Screener-Tabelle '{screener_table_name}' gefunden."
        )
      except Exception as screener_err:
        screener_data_text = (
            f"Konnte Screener-Tabelle '{screener_table_name}' nicht abrufen: {screener_err}"
        )

      # 4. FAVORITEN AUS DER 'favorites'-TABELLE ABRUFEN
      favorites_table_name = "favorites"
      try:
        favorites_res = (
            self.supabase.table(favorites_table_name).select("*").execute()
        )
        favorites_data_text = (
            str(favorites_res.data)
            if favorites_res.data
            else f"Keine Einträge in Favoriten-Tabelle '{favorites_table_name}' gefunden."
        )
      except Exception as favorites_err:
        favorites_data_text = (
            f"Konnte Favoriten-Tabelle '{favorites_table_name}' nicht abrufen: {favorites_err}"
        )

      # System-Instruktion für Joris inklusive TradingView-Regel
      system_instruction = f"""
            Du bist Joris, der leitende Portfolio Manager. 
            Deine Arbeitsweise folgt Ray Dalios Prinzipien: **Radical Truth & Radical Open-Mindedness**.
            Fokus-Mandat: {depot_focus.upper()} (Zugehörige Depot-Tabelle: {table_name})
            
            WICHTIG - MANDATSSPEZIFISCHE ANALYSE-BRILLE:
            - Wenn Fokus 'SWING' ist: Ignoriere fundamentale Bewertungen (KGV, KBV etc.). Konzentriere dich voll auf **technische Indikatoren, Trendstärke, Momentum, Volumen und Chart-Setups** aus dem Screener, den Favoriten und den Kollegen-Berichten.
            - Wenn Fokus 'INVEST' ist: Konzentriere dich auf Fundamentaldaten, Substanz, Bilanzen und langfristiges Core-Holding-Potenzial.
            - Wenn Fokus 'HIGH_RISK' ist: Konzentriere dich auf hochspekulative Setups, explosive Vola und kurzfristige Katalysatoren.
            
            WICHTIG - TRADINGVIEW LINKS:
            Füge bei **jeder** erwähnten Aktie oder Empfehlung (sowohl im Text als auch in Tabellen/Listen) im Markdown-Format einen direkten Link zu TradingView ein. 
            Das Format lautet exakt: `[Ticker](https://www.tradingview.com/chart/?symbol=NASDAQ:TICKER)` (bzw. die entsprechende Börse wie NYSE: oder XETR: falls bekannt, ansonsten Standard-Ticker einsetzen).
            """

      user_prompt = f"""
            DIR LIEGEN FOLGENDE DATEN VOR:
            
            A) AKTUELLER BESTAND DES GEWÄHLTEN DEPOTS ({table_name}):
            {depot_data_text}
            
            B) AKTUELLE SIGNALE AUS DEM SCREENER ({screener_table_name}):
            {screener_data_text}
            
            C) AKTUELLE FAVORITEN ({favorites_table_name}):
            {favorites_data_text}
            
            D) LETZTE BERICHTE DER TEAM-KOLLEGEN (Makro, Insider, History, Performance):
            {reports_text}
            
            DEINE AUFGABE:
            Erstelle eine kompromisslose, datenbasierte Portfolio-Synthese für das Mandat '{depot_focus.upper()}'. Gehe dabei strikt auf folgende Punkte ein:
            1. **Zusammenfassung & Synthese:** Führe die Erkenntnisse der anderen Kollegen im Kontext des aktuellen Marktumfelds zusammen.
            2. **Depot-Prüfung & Diversifikation:** Analysiere das aktuelle Depot ({table_name}) passend zum Mandat.
            3. **Verkaufsempfehlungen:** Benenne glasklar, welche Positionen im Depot reduziert oder komplett abgestoßen werden sollten.
            4. **Top-Empfehlungen des Tages:** Gleiche die Depot-Ziele, die Favoriten und die aktuellen Signale aus dem Screener ab und präsentiere die besten High-Conviction-Kandidaten.
            
            ZUSATZ-FORMAT FÜR DAS JOURNAL (WICHTIG BEI SWING):
            Falls der Fokus 'SWING' ist, liste am Ende deines Reports zwingend einen Block im folgenden exakten JSON-Format auf:
            
            ===JOURNAL_DATA_START===
            [
              {{"ticker": "AAPL", "setup_reason": "Starker Ausbruch über Widerstand mit hohem Volumen", "target": 220.0, "stop_loss": 175.0}},
              {{"ticker": "NVDA", "setup_reason": "Pullback an gleitenden Durchschnitt erfolgreich beendet", "target": 140.0, "stop_loss": 115.0}}
            ]
            ===JOURNAL_DATA_END===
            (Ersetze AAPL/NVDA durch deine echten Top-Picks des Tages aus der Analyse, gib realistische Fließkommazahlen für target und stop_loss an. Falls keine Picks da sind, gib eine leere Liste `[]` aus).
            """

      # Groq API Request mit Llama 3.3 70B
      completion = groq_client.chat.completions.create(
          model="llama-3.1-8b-instant",
          messages=[
              {"role": "system", "content": system_instruction},
              {"role": "user", "content": user_prompt},
          ],
          temperature=0.1,
      )
      report_content = completion.choices[0].message.content

      # 6. In Datenbank speichern (Agenten-Bericht)
      self.supabase.table("agent_reports").insert({
          "agent_name": f"Joris_{depot_focus}",
          "report_content": report_content,
      }).execute()

      # 7. Automatisches, sauberes Schreiben in die joris_journal, falls Fokus SWING ist
      if depot_focus.lower() == "swing":
        try:
          match = re.search(
              r"===JOURNAL_DATA_START===\s*(.*?)\s*===JOURNAL_DATA_END===",
              report_content,
              re.DOTALL,
          )
          if match:
            json_str = match.group(1)
            picks = json.loads(json_str)

            for pick in picks:
              self.supabase.table("joris_journal").insert({
                  "ticker": pick.get("ticker", "UNKNOWN"),
                  "setup_reason": pick.get("setup_reason", "Keine Begründung"),
                  "target": float(pick.get("target", 0.0)),
                  "stop_loss": float(pick.get("stop_loss", 0.0)),
                  "status": "active",
              }).execute()
          else:
            print(
                "Konnte keinen strukturierten Journal-Block im Bericht finden."
            )
        except Exception as watch_err:
          print(f"Konnte joris_journal nicht befüllen: {watch_err}")

      return (
          True,
          f"Synthese inklusive strukturierter Journal-Einträge für '{table_name}' erfolgreich erstellt via Groq!",
      )
    except Exception as e:
      return False, f"Fehler bei der Synthese (Groq): {e}"

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
    """Ermöglicht den Chat mit Joris im Teamroom über Groq."""
    try:
      active_key = api_key if api_key else os.getenv("GROQ_API_KEY")
      groq_client = Groq(api_key=active_key)

      system_msg = (
          f"Du bist Joris, Portfolio Manager für das Depot-Mandat '{depot_focus}'. "
          "Du hast Zugriff auf das Depot, den Screener, die Favoriten und die Team-Berichte. "
          "Passe deine Analyse an das Mandat an (Beim Swing-Mandat Fokus auf Technik/Momentum, "
          "bei Invest auf Fundamentaldaten). Antworte direkt, ehrlich und datenbasiert nach Ray Dalio. "
          "Füge bei genannten Aktien immer einen TradingView-Markdown-Link ein: [Ticker](https://www.tradingview.com/chart/?symbol=TICKER)."
      )

      groq_messages = [{"role": "system", "content": system_msg}]
      for m in chat_history:
        role = "user" if m["role"] == "user" else "assistant"
        groq_messages.append({"role": role, "content": m["content"]})

      groq_messages.append({"role": "user", "content": user_message})

      completion = groq_client.chat.completions.create(
          model="llama-3.3-70b-versatile",
          messages=groq_messages,
          temperature=0.1,
      )
      return True, completion.choices[0].message.content
    except Exception as e:
      return False, f"Chat-Fehler (Groq): {e}"