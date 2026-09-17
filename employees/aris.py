from datetime import datetime, timedelta
import os
from groq import Groq
import pandas as pd
import streamlit as st
from supabase import create_client

# Groq Client / API Key initialisieren
try:
  groq_api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")

  if not groq_api_key:
    raise ValueError(
        "Kein Groq API-Key gefunden. Bitte in den Streamlit Secrets oder als"
        " Environment Variable hinterlegen."
    )

  groq_client = Groq(api_key=groq_api_key)
except Exception as e:
  st.error("Fehler beim Initialisieren des Groq Clients:" f" {e}")

# Aris DNA geschärft auf deine spezifischen Analysepunkte
ARIS_DNA = """
Du bist Aris, der leitende Performance Manager in dieser Trading-Anwendung. Deine Aufgabe ist es, die Performance aus dem Arbeitsspeicher (aris_arbeitsspeicher) objektiv, datenbasiert und gnadenlos ehrlich zu analysieren. Du verzichtest auf leere Floskeln und Schönfärberei.

Fokussiere dich bei jeder Analyse strikt auf folgende Punkte:
1. **ADX & SMI Mustererkennung**: Welche Indikator-Ausprägungen liefern verlässlich gute oder schlechte Ergebnisse?
2. **5-Tage-Vergleich (End vs. Max)**: Laufen die Trades nach 5 Tagen am Endkurs besser oder wird das Maximum (High) besser ausgespielt? (Werden Gewinne zu früh/spät abgegeben?)
3. **Gewinner-Kombinationen**: Gibt es spezifische Signal- oder Indikator-Kombinationen (z.B. bestimmte ADX/SMI-Konstellationen), die überproportional gut performen?
4. **Sonstige Muster & Handlungsempfehlungen**: Was funktioniert am besten, welche Setups sollten gestrichen oder optimiert werden?

Antworte strukturiert, prägnant, datenbasiert und direkt auf den Punkt.
"""

st.subheader("🤖 Aris - Performance Manager")
st.markdown(
    "Dein KI-Agent analysiert die gesammelten Berichte und Signaldaten aus"
    " dem `aris_arbeitsspeicher`."
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
    "🚀 Aris Performance-Analyse starten",
    type="primary",
    key="run_aris_btn",
    use_container_width=True,
):
  with st.spinner(
      "Aris liest den Arbeitsspeicher aus und analysiert die Muster mit"
      " Groq..."
  ):
    try:
      # --- Datenabfrage: Nur noch aus aris_arbeitsspeicher ---
      arbeitsspeicher_res = (
          supabase.table("aris_arbeitsspeicher")
          .select("*")
          .order("created_at", desc=True)
          .limit(50)  # Holt die letzten 50 Einträge zur Mustererkennung
          .execute()
      )

      memory_data = arbeitsspeicher_res.data or []

      if not memory_data:
        st.info(
            "ℹ️ Keine Einträge im `aris_arbeitsspeicher` für Aris vorhanden."
        )
      else:
        # Inhalte für den Prompt aufbereiten
        memory_summaries = []
        for item in memory_data:
          cat = item.get("kategorie", "Allgemein")
          content = item.get("report_content", "")
          created = item.get("created_at", "")[:16]
          memory_summaries.append(f"[{created}] Kategorie: {cat}\n{content}")

        context_data = "\n\n---\n\n".join(memory_summaries)

        # Groq Request
        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": ARIS_DNA},
                {
                    "role": "user",
                    "content": (
                        "Analysiere die folgenden Einträge aus dem"
                        " `aris_arbeitsspeicher`. Untersuche sie gezielt auf"
                        " ADX/SMI-Muster, den Vergleich von 5-Tage-Endkurs"
                        " versus Max-Performance, profitable"
                        " Signal-Kombinationen und allgemeine"
                        " Erfolgsmuster:\n\n"
                        + context_data
                    ),
                },
            ],
            temperature=0.1,
        )

        report_content = completion.choices[0].message.content

        # In Supabase agent_reports speichern
        try:
          supabase.table("agent_reports").insert({
              "agent_name": "Aris",
              "report_content": report_content,
          }).execute()
        except Exception:
          pass

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

if user_query := st.chat_input("Stelle Aris eine Frage zu den Mustern..."):
  st.session_state.messages_aris.append(
      {"role": "user", "content": user_query}
  )
  with st.chat_message("user"):
    st.markdown(user_query)

  with st.chat_message("assistant"):
    with st.spinner("Aris denkt nach..."):
      try:
        groq_history = [
            {"role": "system", "content": ARIS_DNA},
            {
                "role": "system",
                "content": (
                    "PROJEKT-KONTEXT & FOKUS: Du bist datenbasierter"
                    " Performance Manager. Achte strikt auf ADX/SMI-Muster,"
                    " End- vs. Max-Performance nach 5 Tagen und filtere heraus,"
                    " was am besten funktioniert."
                ),
            },
        ]

        # Nur die letzten maximal 6 Nachrichten mitnehmen
        MAX_HISTORY = 6
        recent_messages = st.session_state.messages_aris[-MAX_HISTORY:]

        for m in recent_messages:
          content = m["content"]
          if (
              "**Letzter gespeicherter Report" in content
              or len(content) > 1000
          ):
            content = "[System-Hinweis: Vorheriger Report wurde komprimiert.]"

          role = "user" if m["role"] == "user" else "assistant"
          groq_history.append({"role": role, "content": content})

        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
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