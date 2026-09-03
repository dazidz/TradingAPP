import streamlit as st
from supabase import create_client
from employees.otto import OttoAnalyst

st.set_page_config(layout="wide", page_title="VisionDZ - Teamroom", page_icon="🏢")

if not st.session_state.get("password_correct", False):
    st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
    st.stop()

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

st.title("🏢 VisionDZ - Teamroom (Tägliches Standup)")
st.markdown("Kommandozentrale für **Radical Truth & Radical Open-Mindedness** nach Ray Dalio.")

# --- 1. DEPOT-AUSWAHL FÜR DAS MEETING ---
st.sidebar.markdown("### 🎯 Fokus-Strategie")
selected_depot = st.sidebar.selectbox(
    "Depot für dieses Meeting wählen:",
    ["Invest (Langfristiges Fundament / Core)", "Swing (Mittelfristige Trendfolge)", "Risiko (Aggressive / Spekulative Plays)"]
)

st.info(f"📍 **Aktives Meeting-Depot:** `{selected_depot}` – Alle Analysen und die finale Synthese richten sich nach diesem Portfolio-Profil.")
st.divider()

# Mitarbeiter initialisieren
otto = OttoAnalyst(supabase)

# --- 2. DAS TEAMROOM-MEETING (SYNTHESE & VERGLEICH) ---
st.subheader("🗣️ Team-Diskussion & Perspektiven-Abgleich")
st.caption("Hier prallen die Analysen der KI-Mitarbeiter aufeinander. Keine Ego-Debatten, nur harte Fakten und Dalio-Prinzipien.")

col_otto, col_future = st.columns(2)

# Perspektive Otto
with col_otto:
    st.markdown("#### 📊 Otto (History & Macro)")
    otto_logs = otto.get_logs()
    if otto_logs:
        latest_otto = otto_logs[0]
        st.write(f"**Marktphase:** {latest_otto.get('market_phase', 'N/A')}")
        st.info(latest_otto.get('insight', 'Keine Daten'))
        st.caption(f"Standup vom: {latest_otto.get('analysis_date', 'N/A')}")
    else:
        st.warning("Otto hat noch kein Standup durchgeführt. Starte seine Analyse auf seiner Unterseite.")

# Platzhalter für den nächsten Mitarbeiter (z.B. Risk Manager / Quant)
with col_future:
    st.markdown("#### 🛡️ Risk Manager / Quant (Platzhalter)")
    st.markdown(
        "_Hier wird demnächst der nächste KI-Mitarbeiter seine Kennzahlen "
        "(Volatilität, VaR, Drawdowns) präsentieren, um Ottos Makro-Sicht "
        "kritisch zu hinterfragen._"
    )
    st.info("Status: Bereit für Integration im nächsten Ausbauschritt.")

st.divider()

# --- 3. DIE DALIO-SYNTHESE (ENTSCHLUSS-FINDUNG) ---
st.markdown("### ⚖️ Synthese & Team-Entschluss (Radical Open-Mindedness)")
st.markdown(f"Basierend auf dem aktuellen Standup und dem Fokus auf **{selected_depot}** fassen wir den gemeinsamen Konsens zusammen:")

# Eingabefeld für den finalen CEO-Entschluss oder die kollektive Synthese
team_conclusion = st.text_area(
    "Finaler Team-Beschluss / Nächste Handlungsschritte:",
    placeholder="Z.B.: 'Otto sieht Inflationsdruck, Depot-Ausrichtung für Invest wird defensiver gewichtet, keine neuen High-Risk- Käufe...'"
)

if st.button("💾 Entschluss für dieses Depot festhalten"):
    if team_conclusion:
        try:
            # Hier kannst du den Entschluss in eine Supabase-Tabelle für Team-Entschlüsse speichern
            supabase.table("team_decisions").insert({
                "depot_focus": selected_depot,
                "decision_text": team_conclusion
            }).execute()
            st.success("Der Team-Entschluss wurde erfolgreich im System verankert!")
        except Exception as e:
            st.error(f"Fehler beim Speichern (existiert die Tabelle 'team_decisions' in Supabase?): {e}")
    else:
            st.warning("Bitte trage einen Entschluss ein.")