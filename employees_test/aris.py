import streamlit as st
import google.generativeai as genai
import os

AGENT_TITLE = "Aris (Performance)"

def render_ui(supabase, get_gemini_api_key):
    st.subheader("🤖 Aris - Performance Manager (Test)")
    st.caption("🤖 **Verwendetes Modell:** Google Gemini (`gemini-3.6-flash`)")
    st.markdown("Dein KI-Agent analysiert ausschließlich den `aris_arbeitsspeicher` und steht im Chat zur Verfügung.")

    if "messages_aris_test" not in st.session_state:
        st.session_state.messages_aris_test = []

    aris_dna = """
    Du bist Aris, der leitende Performance Manager in dieser Trading-Anwendung. Deine Aufgabe ist es, die Performance objektiv, datenbasiert und gnadenlos ehrlich zu analysieren. Du verzichtest auf leere Floskeln und Schönfärberei. 
    Analysiere die übergebenen Datenpunkte aus dem Arbeitsspeicher.
    Finde Muster, vergleiche Gewinner vs. Verlierer, bewerte ob Trades zu früh geschlossen wurden und liefere konkrete, direkt umsetzbare Handlungsempfehlungen.
    """

    # Robuste Hilfsfunktion, um den API-Key sicher zu greifen
    def resolve_key():
        try:
            if callable(get_gemini_api_key):
                val = get_gemini_api_key()
                if val:
                    return val
            elif isinstance(get_gemini_api_key, str) and get_gemini_api_key:
                return get_gemini_api_key
        except Exception:
            pass
        
        # Fallback auf Secrets oder Umgebungsvariablen
        try:
            if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
                if st.secrets["GEMINI_API_KEY"]:
                    return st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass
            
        if os.getenv("GEMINI_API_KEY"):
            return os.getenv("GEMINI_API_KEY")
            
        return None

    # Letzten gespeicherten Report laden (falls vorhanden)
    if not st.session_state.messages_aris_test:
        try:
            saved_report_res = (
                supabase.table("agent_reports")
                .select("*")
                .eq("agent_name", "Aris (Test)")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if saved_report_res.data:
                latest_report = saved_report_res.data[0]
                st.session_state.messages_aris_test.append({
                    "role": "assistant",
                    "content": (
                        "**Letzter gespeicherter Report ("
                        f"{latest_report['created_at'][:16]}):**\n\n"
                        + latest_report["report_content"]
                    ),
                })
        except Exception:
            pass

    if st.button("🚀 Aris Analyse & Arbeitsspeicher-Review starten", type="primary", key="btn_run_aris_test_clean"):
        with st.spinner("Aris (Gemini) analysiert den Arbeitsspeicher..."):
            try:
                active_k = resolve_key()
                if not active_k:
                    st.error("⚠️ Kein Gemini API-Key gefunden.")
                    st.stop()

                genai.configure(api_key=active_k)
                model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=aris_dna)

                # 1. EXKLUSIV: Nur aris_arbeitsspeicher auslesen
                res = supabase.table("aris_arbeitsspeicher").select("*").execute()
                items = res.data or []

                if not items:
                    st.warning("⚠️ Keine Einträge im `aris_arbeitsspeicher` gefunden.")
                    st.stop()

                # 2. Daten kompakt aufbereiten
                formatted_lines = []
                for item in items:
                    row_str = " | ".join([f"{k}: {v}" for k, v in item.items() if k != "id"])
                    formatted_lines.append(f"- {row_str}")

                data_payload = "\n".join(formatted_lines)
                prompt = f"Analysiere bitte die folgenden aktuellen Einträge aus dem Arbeitsspeicher:\n\n{data_payload}"

                # 3. Gemini Abfrage
                response = model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.1}
                )
                report_content = response.text

                # 4. In agent_reports speichern
                supabase.table("agent_reports").insert({
                    "agent_name": "Aris (Test)",
                    "report_content": report_content,
                }).execute()

                # 5. Arbeitsspeicher bereinigen (Einträge löschen)
                for item in items:
                    if "id" in item:
                        supabase.table("aris_arbeitsspeicher").delete().eq("id", item["id"]).execute()

                st.session_state.messages_aris_test.append(
                    {"role": "assistant", "content": report_content}
                )
                st.success("Analyse erfolgreich abgeschlossen & Arbeitsspeicher bereinigt!")
                st.rerun()

            except Exception as e:
                st.error(f"⚠️ Fehler bei der Aris-Analyse: {e}")

    st.markdown("---")
    st.markdown("### 💬 Test-Diskussion mit Aris")

    for message in st.session_state.messages_aris_test:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input("Stelle Aris eine Frage...", key="aris_chat_input_test_clean"):
        st.session_state.messages_aris_test.append(
            {"role": "user", "content": user_query}
        )
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Aris (Gemini) denkt nach..."):
                try:
                    active_k = resolve_key()
                    if not active_k:
                        st.error("⚠️ Kein Gemini API-Key gefunden.")
                        st.stop()

                    genai.configure(api_key=active_k)
                    
                    gemini_history = []
                    for m in st.session_state.messages_aris_test[:-1]:
                        role = "user" if m["role"] == "user" else "model"
                        gemini_history.append({"role": role, "parts": [m["content"]]})

                    model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=aris_dna)
                    chat_session = model.start_chat(history=gemini_history)
                    
                    response = chat_session.send_message(user_query)
                    answer = response.text

                    st.markdown(answer)
                    st.session_state.messages_aris_test.append(
                        {"role": "assistant", "content": answer}
                    )
                except Exception as chat_err:
                    st.error(f"Fehler im Chat: {chat_err}")