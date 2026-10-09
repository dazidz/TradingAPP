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
        st.markdown("Exakte Kombinationen-Filterung (ADX x SMI), Timing-Optimierung & Heatmap des `signals_journal`.")
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

            # --- UI: SIGNAL-TYP FILTER (VORAB) ---
            st.markdown("### 🎛️ 1. Grundfilter")
            col_f1, _ = st.columns([2, 2])
            with col_f1:
                if type_col:
                    unique_types = ["Alle"] + sorted(list(df_sj[type_col].dropna().unique()))
                    sel_type = st.selectbox("Signal-Typ", unique_types, key="leopold_type_filter")
                else:
                    sel_type = "Alle"

            # Grundfilter anwenden
            df_base = df_sj.copy()
            if type_col and sel_type != "Alle":
                df_base = df_base[df_base[type_col] == sel_type]

            # --- ZONEN SICHER DEFINIEREN ---
            df_base["ADX_Zone"] = "ADX: N/A"
            df_base["SMI_Zone"] = "SMI: N/A"

            if adx_col and not df_base.empty:
                valid_adx = df_base[adx_col].dropna()
                if len(valid_adx) >= 4:
                    try:
                        df_base.loc[valid_adx.index, "ADX_Zone"] = pd.qcut(
                            valid_adx, q=4, labels=["ADX: Q1 (Tief)", "ADX: Q2 (Med-Tief)", "ADX: Q3 (Med-Hoch)", "ADX: Q4 (Stark)"], duplicates="drop"
                        ).astype(str)
                    except Exception:
                        df_base.loc[valid_adx.index, "ADX_Zone"] = "ADX: Standard"

            if smi_col and not df_base.empty:
                valid_smi = df_base[smi_col].dropna()
                if len(valid_smi) >= 4:
                    try:
                        df_base.loc[valid_smi.index, "SMI_Zone"] = pd.qcut(
                            valid_smi, q=4, labels=["SMI: Q1 (Tief)", "SMI: Q2 (Med-Tief)", "SMI: Q3 (Med-Hoch)", "SMI: Q4 (Hoch)"], duplicates="drop"
                        ).astype(str)
                    except Exception:
                        df_base.loc[valid_smi.index, "SMI_Zone"] = "SMI: Standard"

            st.markdown("### 🧬 2. Exakte Kombinations-Auswahl (ADX x SMI Matrix)")
            st.markdown("Wähle hier per Checkbox aus, **welche konkreten Kombinationen** (Schnittmengen aus ADX- und SMI-Zone) in die Auswertung einfließen sollen:")

            adx_labels = sorted(list(df_base["ADX_Zone"].astype(str).unique()))
            smi_labels = sorted(list(df_base["SMI_Zone"].astype(str).unique()))

            if "combo_selections" not in st.session_state:
                st.session_state.combo_selections = {}

            # UI-Matrix als Checkbox-Raster
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
            if active_combinations and not df_base.empty:
                mask = df_filtered.apply(lambda row: (str(row["ADX_Zone"]), str(row["SMI_Zone"])) in active_combinations, axis=1)
                df_filtered = df_filtered[mask]
            else:
                df_filtered = pd.DataFrame(columns=df