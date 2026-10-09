from datetime import datetime, timedelta
import pandas as pd
import json
import altair as alt
import streamlit as st

AGENT_TITLE = "Leopold"

class LeopoldAnalyticsManager:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Leopold"
        self.description = "Signals Journal & Deep Analytics"

    def render_ui(self, api_key=None):
        st.subheader(f"⚙️ {self.name} - {self.description}")
        st.markdown("Exakte Kombinationen-Filterung (ADX x SMI) & Timing-Optimierung des `signals_journal`.")
        st.divider()

        # Daten aus signals_journal laden (mit Paginierung, um das 1000er-Limit zu umgehen)
        sj_data = []
        load_error = None
        try:
            page_size = 1000
            offset = 0
            while True:
                res = self.supabase.table("signals_journal").select("*").range(offset, offset + page_size - 1).execute()
                batch = res.data if res and res.data else []
                sj_data.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
        except Exception as e:
            load_error = str(e)

        if load_error:
            st.error(f"⚠️ Supabase-Fehler beim Zugriff auf `signals_journal`: {load_error}")
        elif not sj_data:
            st.warning("⚠️ Die Tabelle `signals_journal` ist aktuell **leer**.")
        else:
            df_sj = pd.DataFrame(sj_data)

            # Meta-Data entpacken, falls ADX/SMI/Timing darin gespeichert sind
            if "meta_data" in df_sj.columns:
                def parse_meta(x):
                    if isinstance(x, dict):
                        return x
                    if isinstance(x, str) and x.startswith("{"):
                        try:
                            return json.loads(x.replace("'", '"'))
                        except Exception:
                            return {}
                    return {}
                
                meta_parsed = df_sj["meta_data"].apply(parse_meta)
                if not meta_parsed.empty and any(meta_parsed.apply(lambda d: len(d) > 0)):
                    meta_df = pd.json_normalize(meta_parsed)
                    meta_df = meta_df[[c for c in meta_df.columns if c not in df_sj.columns]]
                    df_sj = pd.concat([df_sj, meta_df], axis=1)

            # Spalten-Erkennung absichern
            possible_type_cols = ["signal_typ", "typ", "signal_type", "type"]
            type_col = next((c for c in possible_type_cols if c in df_sj.columns), None)

            adx_col = next((c for c in ["adx", "average_directional_index", "adx_value"] if c in df_sj.columns), None)
            smi_col = next((c for c in ["smi", "stochastic_momentum_index", "smi_value"] if c in df_sj.columns), None)

            if type_col:
                df_sj[type_col] = df_sj[type_col].astype(str).str.strip()

            if adx_col:
                df_sj[adx_col] = pd.to_numeric(df_sj[adx_col], errors="coerce")
            if smi_col:
                df_sj[smi_col] = pd.to_numeric(df_sj[smi_col], errors="coerce")

            # --- ZONEN DEFINIEREN (QUARTILE) ---
            if adx_col and not df_sj[adx_col].dropna().empty:
                df_sj["ADX_Zone"] = pd.qcut(df_sj[adx_col], q=4, labels=["ADX: Q1 (Tief)", "ADX: Q2 (Med-Tief)", "ADX: Q3 (Med-Hoch)", "ADX: Q4 (Stark)"], duplicates="drop")
            else:
                df_sj["ADX_Zone"] = "Kein ADX"

            if smi_col and not df_sj[smi_col].dropna().empty:
                df_sj["SMI_Zone"] = pd.qcut(df_sj[smi_col], q=4, labels=["SMI: Q1 (Tief)", "SMI: Q2 (Med-Tief)", "SMI: Q3 (Med-Hoch)", "SMI: Q4 (Hoch)"], duplicates="drop")
            else:
                df_sj["SMI_Zone"] = "Kein SMI"

            # --- UI: SIGNAL-TYP FILTER ---
            st.markdown("### 🎛️ 1. Grundfilter")
            col_f1, _ = st.columns([2, 2])
            with col_f1:
                if type_col:
                    unique_types = ["Alle"] + sorted(list(df_sj[type_col].dropna().unique()))
                    sel_type = st.selectbox("Signal-Typ", unique_types, key="leopold_type_filter")
                else:
                    sel_type = "Alle"

            # Grundfilter anwenden für die Zonen-Ermittlung
            df_base = df_sj.copy()
            if type_col and sel_type != "Alle":
                df_base = df_base[df_base[type_col] == sel_type]

            st.markdown("### 🧬 2. Exakte Kombinations-Auswahl (ADX x SMI Matrix)")
            st.markdown("Wähle hier per Checkbox aus, **welche konkreten Kombinationen** (Schnittmengen aus ADX- und SMI-Zone) in die Auswertung einfließen sollen:")

            # Erstelle eine Matrix aller möglichen Kombinationen
            adx_labels = sorted(list(df_base["ADX_Zone"].astype(str).unique()))
            smi_labels = sorted(list(df_base["SMI_Zone"].astype(str).unique()))

            # Initialsierung der Session State für Kombinationen, falls noch nicht geschehen
            if "combo_selections" not in st.session_state:
                st.session_state.combo_selections = {}

            # UI-Matrix als Tabelle / Checkbox-Raster
            cols_matrix = st.columns(len(smi_labels) + 1)
            with cols_matrix[0]:
                st.markdown("**ADX \\ SMI**")
            for idx, smi_lbl in enumerate(smi_labels):
                with cols_matrix[idx + 1]:
                    st.markdown(f"**{smi_lbl.split(' ')[-1]}**")

            active_combinations = []
            for adx_lbl in adx_labels:
                row_cols = st.columns(len(smi_labels) + 1)
                with row_cols[0]:
                    st.markdown(f"**{adx_lbl}**")
                
                for idx, smi_lbl in enumerate(smi_labels):
                    combo_key = f"{adx_lbl}__AND__{smi_lbl}"
                    # Standardmäßig auf True (oder False) setzen
                    if combo_key not in st.session_state.combo_selections:
                        st.session_state.combo_selections[combo_key] = True
                    
                    with row_cols[idx + 1]:
                        is_checked = st.checkbox("", value=st.session_state.combo_selections[combo_key], key=f"cb_{combo_key}", label_visibility="collapsed")
                        st.session_state.combo_selections[combo_key] = is_checked
                        if is_checked:
                            active_combinations.append((adx_lbl, smi_lbl))

            st.divider()

            # --- FILTER ANWENDEN AUF BASIS DER GEWÄHLTEN KOMBINATIONEN ---
            df_filtered = df_base.copy()
            if active_combinations:
                # Filtere Zeilen, deren (ADX_Zone, SMI_Zone) Tupel in den aktiven Kombinationen enthalten ist
                mask = df_filtered.apply(lambda row: (str(row["ADX_Zone"]), str(row["SMI_Zone"])) in active_combinations, axis=1)
                df_filtered = df_filtered[mask]
            else:
                df_filtered = pd.DataFrame(columns=df_base.columns) # Nichts ausgewählt

            # Teilmengen für Elite vs. Kauf
            if type_col:
                df_elite = df_filtered[df_filtered[type_col].str.lower().str.contains("elite", na=False)]
                df_kauf = df_filtered[df_filtered[type_col].str.lower().str.contains("kauf|buy", na=False)]
            else:
                df_elite = pd.DataFrame()
                df_kauf = pd.DataFrame()

            def safe_mean(dataframe, column_name):
                if not dataframe.empty and column_name in dataframe.columns:
                    val = pd.to_numeric(dataframe[column_name], errors='coerce').mean()
                    return val if pd.notnull(val) else 0.0
                return 0.0

            perf_target_col = next((c for c in ["end_performance_5_tage", "performance", "end_performance"] if c in df_sj.columns), None)
            max_perf_col = next((c for c in ["max_performance_5_tage", "mfe", "max_performance"] if c in df_sj.columns), None)
            drawdown_col = next((c for c in ["max_drawdown", "mae", "drawdown"] if c in df_sj.columns), None)
            days_col = next((c for c in ["tage_bis_max_perf", "days_to_max", "max_perf_tage", "tage_bis_max"] if c in df_sj.columns), None)

            perf_elite = safe_mean(df_elite, perf_target_col)
            perf_kauf = safe_mean(df_kauf, perf_target_col)

            win_rate = 0.0
            if not df_filtered.empty and perf_target_col:
                numeric_perf = pd.to_numeric(df_filtered[perf_target_col], errors='coerce')
                winning_trades = (numeric_perf > 0).sum()
                total_valid_trades = numeric_perf.dropna().count()
                if total_valid_trades > 0:
                    win_rate = (winning_trades / total_valid_trades) * 100

            avg_days_to_max = safe_mean(df_filtered, days_col)
            avg_max_perf = safe_mean(df_filtered, max_perf_col)
            avg_drawdown = safe_mean(df_filtered, drawdown_col)

            # --- KPI METRIKEN (INKL. TIMING) ---
            st.markdown("### 📊 Performance- & Timing-Kennzahlen (für gewählte Kombinationen)")
            
            r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
            with r1_c1: st.metric("Win-Rate (Quote)", f"{win_rate:.1f}%")
            with r1_c2: st.metric("Ø Max. Performance (MFE)", f"{avg_max_perf:+.2f}%")
            with r1_c3: st.metric("Ø Max. Drawdown (MAE)", f"{avg_drawdown:+.2f}%")
            with r1_c4: st.metric("Ø Tage bis Peak-Perf.", f"{avg_days_to_max:.1f} Tage")

            st.divider()

            # --- TABELLE & DOWNLOAD ---
            st.subheader(f"📋 Gefiltertes Signals Journal ({len(df_filtered)} Einträge)")
            st.dataframe(df_filtered, use_container_width=True, hide_index=True)

            csv_data = df_filtered.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Gefiltertes Signals Journal als CSV herunterladen",
                data=csv_data,
                file_name="signals_journal_combinations_export.csv",
                mime="text/csv",
            )


def render_ui(supabase_client, api_key=None):
    agent = LeopoldAnalyticsManager(supabase_client)
    agent.render_ui(api_key)