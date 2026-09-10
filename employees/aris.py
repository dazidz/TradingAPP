from datetime import datetime, timedelta
from pathlib import Path
from groq import Groq
import pandas as pd
import streamlit as st
from supabase import create_client
import yfinance as yf

# Groq Client / API Key initialisieren
try:
  # Versuche den Key aus den Streamlit-Secrets oder den Umgebungsvariablen zu holen
  groq_api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")

  if not groq_api_key:
    raise ValueError(
        "Kein Groq API-Key gefunden. Bitte in den Streamlit Secrets oder als"
        " Environment Variable hinterlegen."
    )

  groq_client = Groq(api_key=groq_api_key)
except Exception as e:
  st.error(
      "Fehler beim Initialisieren des Groq Clients:" f" {e}"
  )

ARIS_DNA = """
Du bist Aris, der leitende Performance Manager in dieser Trading-Anwendung. Deine Aufgabe ist es, die Performance objektiv, datenbasiert und gnadenlos ehrlich zu analysieren. Du verzichtest auf leere Floskeln und Schönfärberei. 
Analysiere die übergebenen Datenpunkte:
1. Signals Journal (inkl. 5-Tage und 1-Monats-Meilensteine)
2. Trading Journal (geschlossene Trades inkl. Post-Exit-Tracking)
3. Joris Journal / Swing-Watchlist (von Joris vorgeschlagene Swing-Setups auf Qualität, Setup-Grund, Ziele und Stopps prüfen)
4. Screener-Quellcode (auf Filterfehler, Schwachstellen und verpasste Chancen prüfen)
5. Watchlist (nach Asset-Kategorien: Invest, Swing, High Risk)

Finde Muster, vergleiche Gewinner vs. Verlierer, bewerte ob Trades zu früh geschlossen wurden und liefere konkrete, direkt umsetzbare Handlungsempfehlungen. Wenn du Code-Verbesserungen oder eiserne Regeln findest, formuliere sie klar, damit sie in die 'principles_and_insights'-Tabelle übernommen werden können.
Antworte strukturiert, prägnant und auf den Punkt.
"""

st.subheader("🤖 Aris - Performance Manager")
st.markdown(
    "Dein KI-Agent analysiert das Signals-Journal, das Trading-Journal, das Joris-Journal, "
    "den Screener-Quellcode und steht dir im Chat für Rückfragen zur Verfügung."
)

# 1. Session State für den Aris-Chat initialisieren
if "messages_aris" not in st.session_state:
  st.session_state.messages_aris = []

# 0. Gespeicherten Report aus Supabase laden (falls noch kein Chat da ist)
try:
  saved_report_res = (
      supabase.table("agent_reports")
      .select("*")
      .eq("agent_name", "Aris")
      .order("created_at", desc=True)
      .limit(1)
      .execute()
  )
  if saved_report_res.data and not st.session_state.messages_aris:
    latest_report = saved_report_res.data[0]
    st.session_state.messages_aris.append({
        "role": "assistant",
        "content": (
            "**Letzter gespeicherter Report ("
            f"{latest_report['created_at'][:16]}):**\n\n"
            + latest_report["report_content"]
        ),
    })
except Exception:
  pass

# Button zum Ausführen der Hauptanalyse
if st.button(
    "🚀 Aris Analyse & Screener-Review starten",
    type="primary",
    key="run_aris_btn",
    use_container_width=True,
):
  with st.spinner(
      "Aris analysiert Datenbanken, liest Screener-Code ein und prüft"
      " Meilensteine mit Groq (Llama 3.3 70B)..."
  ):
    try:
      # --- Datenabfrage ---
      signals_res = (
          supabase.table("signals_journal")
          .select("*")
          .eq("aris_status_5d", False)
          .execute()
      )
      journal_res = (
          supabase.table("trading_journal")
          .select("*")
          .eq("aris_status_5d", False)
          .execute()
      )
      watchlist_res = supabase.table("watchlist").select("*").execute()
      
      # NEU: joris_journal abrufen
      joris_journal_res = supabase.table("joris_journal").select("*").execute()

      signals_df = pd.DataFrame(signals_res.data)
      journal_df = pd.DataFrame(journal_res.data)
      watchlist_df = pd.DataFrame(watchlist_res.data)
      joris_journal_df = pd.DataFrame(joris_journal_res.data)

      # Screener-Code einlesen
      screener_code_content = ""
      try:
        screener_path = Path("screeners/main_screener.py")
        if screener_path.exists():
          screener_code_content = screener_path.read_text(encoding="utf-8")
        else:
          screener_files = list(Path(".").glob("**/*screener*.py"))
          if screener_files:
            screener_code_content = screener_files[0].read_text(encoding="utf-8")
      except Exception as code_err:
        screener_code_content = f"Konnte Screener-Code nicht laden: {code_err}"

      # Post-Exit Tracking
      post_exit_results = []
      if not journal_df.empty and "ausstieg_datum_zeit" in journal_df.columns:
        for _, row in journal_df.head(20).iterrows():
          ticker = row.get("ticker")
          exit_date_str = row.get("ausstieg_datum_zeit")
          exit_price = float(row.get("ausstiegskurs", 0))
          try:
            exit_date = pd.to_datetime(exit_date_str)
            end_date = exit_date + timedelta(days=30)
            df_post = yf.download(
                ticker,
                start=exit_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
            if not df_post.empty and "Close" in df_post:
              max_post_price = float(df_post["Close"].max())
              perf_after = (
                  ((max_post_price - exit_price) / exit_price) * 100
                  if exit_price > 0
                  else 0
              )
              post_exit_results.append({
                  "ticker": ticker,
                  "ausstieg_preis": exit_price,
                  "max_preis_30d_danach": max_post_price,
                  "verpasste_bewegung_%": round(perf_after, 2),
              })
          except Exception:
            continue

      # Watchlist Extremwerte
      top_winners, top_losers = [], []
      if not watchlist_df.empty:
        watchlist_df["perf_titel"] = pd.to_numeric(
            watchlist_df.get("performance", 0), errors="coerce"
        )
        sorted_wl = watchlist_df.sort_values(by="perf_titel", ascending=False)
        top_winners = sorted_wl.head(10).to_dict(orient="records")
        top_losers = sorted_wl.tail(10).to_dict(orient="records")

      # Kontext bündeln (Inklusive joris_journal)
      context_data = f"""
            --- SIGNALS JOURNAL ---
            {signals_df.to_string() if not signals_df.empty else "Keine neuen Signale"}

            --- TRADING JOURNAL ---
            {journal_df.to_string() if not journal_df.empty else "Keine offenen Journal-Einträge"}

            --- JORIS JOURNAL ---
            {joris_journal_df.to_string() if not joris_journal_df.empty else "Keine Joris-Journal-Einträge"}

            --- POST-EXIT TRACKING ---
            {pd.DataFrame(post_exit_results).to_string() if post_exit_results else "Keine Daten"}

            --- SCREENER-QUELLCODE ---
            {screener_code_content if screener_code_content else "Kein Code gefunden"}

            --- WATCHLIST TOP GEWINNER / VERLIERER ---
            Gewinner:\n{pd.DataFrame(top_winners).to_string() if top_winners else "Keine"}
            Verlierer:\n{pd.DataFrame(top_losers).to_string() if top_losers else "Keine"}
            """

      # Groq Request mit Llama 3.3 70B (starkes Logik- & Code-Modell)
      completion = groq_client.chat.completions.create(
          model="llama-3.3-70b-versatile",
          messages=[
              {"role": "system", "content": ARIS_DNA},
              {
                  "role": "user",
                  "content": (
                      "Erstelle deinen Analyse-Report basierend auf folgenden Daten:\n\n"
                      + context_data
                  ),
              },
          ],
          temperature=0.1,
      )

      report_content = completion.choices[0].message.content

      # In Supabase speichern
      try:
        supabase.table("agent_reports").insert({
            "agent_name": "Aris",
            "report_content": report_content,
        }).execute()
      except Exception:
        pass

      # Status aktualisieren
      if not signals_df.empty and "id" in signals_df.columns:
        supabase.table("signals_journal").update({"aris_status_5d": True}).in_(
            "id", signals_df["id"].tolist()
        ).execute()
      if not journal_df.empty and "id" in journal_df.columns:
        supabase.table("trading_journal").update({"aris_status_5d": True}).in_(
            "id", journal_df["id"].tolist()
        ).execute()

      st.session_state.messages_aris.append(
          {"role": "assistant", "content": report_content}
      )
      st.success("Analyse erfolgreich abgeschlossen!")
      st.rerun()

    except Exception as e:
      st.error(f"⚠️ Fehler: {e}")

st.markdown("---")
st.markdown("### 💬 Diskussion mit Aris")

for message in st.session_state.messages_aris:
  with st.chat_message(message["role"]):
    st.markdown(message["content"])

if user_query := st.chat_input(
    "Stelle Aris eine Frage zu den Trades oder dem Code..."
):
  st.session_state.messages_aris.append(
      {"role": "user", "content": user_query}
  )
  with st.chat_message("user"):
    st.markdown(user_query)

  with st.chat_message("assistant"):
    with st.spinner("Aris denkt nach..."):
      try:
        groq_history = [{"role": "system", "content": ARIS_DNA}]
        for m in st.session_state.messages_aris[:-1]:
          role = "user" if m["role"] == "user" else "assistant"
          groq_history.append({"role": role, "content": m["content"]})

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=groq_history,
            temperature=0.1,
        )

        answer = completion.choices[0].message.content
        st.markdown(answer)

        st.session_state.messages_aris.append(
            {"role": "assistant", "content": answer}
        )
      except Exception as chat_err:
        st.error(f"Fehler im Chat: {chat_err}")