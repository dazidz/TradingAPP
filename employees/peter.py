from datetime import datetime, timedelta
from pathlib import Path
from groq import Groq
import pandas as pd
import streamlit as st
from supabase import create_client
import yfinance as yf

# Groq Client / API Key initialisieren (mit deinem bereitgestellten Key)
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

PETER_DNA = """
Du bist Peter, der Micro- & Insider-Analyst in dieser Trading-Anwendung. Deine Aufgabe ist es, Live-Daten, Marktnachrichten, Insider-Aktivitäten und Mikro-Faktoren objektiv und präzise zu analysieren. Du verzichtest auf leere Floskeln und Schönfärberei. 
Analysiere die übergebenen Live-Daten und News-Ausschnitte. Finde Anomalien, Insider-Käufe/-Verkäufe, Sentiment-Verschiebungen und liefere konkrete, direkt umsetzbare Erkenntnisse.
Antworte strukturiert, prägnant und auf den Punkt.
"""

st.subheader("🤖 Peter - Micro & Insider Analyst")
st.markdown(
    "Dein KI-Agent analysiert Live-Daten, News und Insider-Aktivitäten "
    "und steht dir im Chat für Rückfragen zur Verfügung."
)

# 1. Session State für den Peter-Chat initialisieren
if "messages_peter" not in st.session_state:
  st.session_state.messages_peter = []

# 0. Gespeicherten Report aus Supabase laden (falls noch kein Chat da ist)
try:
  saved_report_res = (
      supabase.table("agent_reports")
      .select("*")
      .eq("agent_name", "Peter")
      .order("created_at", desc=True)
      .limit(1)
      .execute()
  )
  if saved_report_res.data and not st.session_state.messages_peter:
    latest_report = saved_report_res.data[0]
    st.session_state.messages_peter.append({
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
    "🚀 Peter Live-Analyse starten",
    type="primary",
    key="run_peter_btn",
    use_container_width=True,
):
  with st.spinner(
      "Peter ruft Live-Daten ab und analysiert mit Groq (Llama 3.1)..."
  ):
    try:
      # --- Live-Datenabfrage über yfinance (Beispielhaft für Watchlist / Top-Ticker) ---
      watchlist_res = supabase.table("watchlist").select("ticker").execute()
      tickers = [row["ticker"] for row in watchlist_res.data] if watchlist_res.data else ["AAPL", "MSFT", "NVDA"]
      
      live_market_data = []
      for t in tickers[:10]: # Limitiert auf die ersten 10 für Performance
        try:
          ticker_obj = yf.Ticker(t)
          hist = ticker_obj.history(period="5d")
          if not hist.empty:
            last_close = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last_close
            change_pct = ((last_close - prev_close) / prev_close) * 100
            live_market_data.append({
                "ticker": t,
                "last_close": round(last_close, 2),
                "change_pct_5d": round(change_pct, 2)
            })
        except Exception:
          continue

      context_data = f"""
            --- LIVE MARKT DATEN (yfinance) ---
            {pd.DataFrame(live_market_data).to_string() if live_market_data else "Keine Live-Daten verfügbar"}
            """

      # Groq Request (Llama 3.1 8B Instant)
      completion = groq_client.chat.completions.create(
          model="llama-3.1-8b-instant",
          messages=[
              {"role": "system", "content": PETER_DNA},
              {
                  "role": "user",
                  "content": (
                      "Erstelle deinen Analyse-Report basierend auf folgenden Live-Daten:\n\n"
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
            "agent_name": "Peter",
            "report_content": report_content,
        }).execute()
      except Exception:
        pass

      st.session_state.messages_peter.append(
          {"role": "assistant", "content": report_content}
      )
      st.success("Analyse erfolgreich abgeschlossen!")
      st.rerun()

    except Exception as e:
      st.error(f"⚠️ Fehler: {e}")

st.markdown("---")
st.markdown("### 💬 Diskussion mit Peter")

for message in st.session_state.messages_peter:
  with st.chat_message(message["role"]):
    st.markdown(message["content"])

if user_query := st.chat_input(
    "Stelle Peter eine Frage zu Live-Daten oder News..."
):
  st.session_state.messages_peter.append(
      {"role": "user", "content": user_query}
  )
  with st.chat_message("user"):
    st.markdown(user_query)

  with st.chat_message("assistant"):
    with st.spinner("Peter denkt nach..."):
      try:
        groq_history = [{"role": "system", "content": PETER_DNA}]
        for m in st.session_state.messages_peter[:-1]:
          role = "user" if m["role"] == "user" else "assistant"
          groq_history.append({"role": role, "content": m["content"]})

        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=groq_history,
            temperature=0.1,
        )

        answer = completion.choices[0].message.content
        st.markdown(answer)

        st.session_state.messages_peter.append(
            {"role": "assistant", "content": answer}
        )
      except Exception as chat_err:
        st.error(f"Fehler im Chat: {chat_err}")