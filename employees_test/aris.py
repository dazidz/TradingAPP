import streamlit as st
import google.generativeai as genai
import os

AGENT_TITLE = "Aris (Performance)"

def render_ui(supabase, get_gemini_api_key):
    st.subheader("🤖 Aris - Performance Manager (Test)")
    st.caption("🤖 **Verwendetes Modell:** Google Gemini (`gemini-3.6-flash`)")
    st.markdown("Dein KI-Agent analysiert den Arbeitsspeicher und steht im Chat zur Verfügung.")

    if "messages_aris_test" not in st.session_state:
        st.session_state.messages_aris_test = []

    aris_dna = """
    Du bist Aris, der leitende Performance Manager in dieser Trading-Anwendung. Deine Aufgabe ist es, die Performance objektiv, datenbasiert und gnadenlos ehrlich zu analysieren.
    """

    if st.button("🚀 Aris Analyse & Arbeitsspeicher-Review starten (Test)", type="primary", key="btn_run_aris_test"):
        with st.spinner("Aris (Gemini) analysiert den Arbeitsspeicher..."):
            try:
                active_k = get_gemini_api_key()
                if not active_k:
                    st.error("⚠️ Kein Gemini API-Key gefunden.")
                    st.stop()

                genai.configure(api_key=active_k)
                model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=aris_dna)

                res = supabase.table("aris_arbeitsspeicher").select("*").execute()
                items = res.data or []

                if not items:
                    st.warning("⚠️ Keine Einträge im `aris_arbeitsspeicher` gefunden.")
                    st.stop()

                formatted_lines = [f"- " + " | ".join([f"{k}: {v}" for k, v in item.items() if k != "id"]) for item in items]
                prompt = f"Analysiere bitte die folgenden aktuellen Einträge aus dem Arbeitsspeicher:\n\n{'\n'.join(formatted_lines)}"

                response = model.generate_content(prompt, generation_config={"temperature": 0.1})
                report_content = response.text

                supabase.table("agent_reports").insert({
                    "agent_name": "Aris (Test)",
                    "report_content": report_content,
                }).execute()

                for item in items:
                    if "id" in item:
                        supabase.table("aris_arbeitsspeicher").delete().eq("id", item["id"]).execute()

                st.session_state.messages_aris_test.append({"role": "assistant", "content": report_content})
                st.success("Test-Analyse erfolgreich abgeschlossen!")
                st.rerun()

            except Exception as e:
                st.error(f"⚠️ Fehler bei der Aris-Analyse: {e}")

    st.markdown("---")
    st.markdown("### 💬 Test-Diskussion mit Aris")

    for message in st.session_state.messages_aris_test:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input("Stelle Aris eine Frage (Test)...", key="aris_chat_input_test"):
        st.session_state.messages_aris_test.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Aris (Gemini) denkt nach..."):
                try:
                    active_k = get_gemini_api_key()
                    genai.configure(api_key=active_k)
                    
                    gemini_history = [{"role": ("user" if m["role"] == "user" else "model"), "parts": [m["content"]]} for m in st.session_state.messages_aris_test[:-1]]
                    model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=aris_dna)
                    chat_session = model.start_chat(history=gemini_history)
                    
                    answer = chat_session.send_message(user_query).text
                    st.markdown(answer)
                    st.session_state.messages_aris_test.append({"role": "assistant", "content": answer})
                except Exception as chat_err:
                    st.error(f"Fehler im Chat: {chat_err}")