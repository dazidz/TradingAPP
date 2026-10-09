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
        st.markdown("Vollständige Auswertung, Indikatoren-Analyse (ADX & SMI) und Sweet-Spot-Identifikation des `signals_journal`.")
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

            # Meta-Data entpacken, falls ADX/SMI darin gespeichert sind
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

            # --- FILTER-OPTIONEN IN DER UI ---
            st.markdown("### 🎛️ Filter & Analyse-Parameter")
            col_f1, col_f2, col_f3 = st.columns(3)

            with col_f1:
                if type_col:
                    unique_types = ["Alle"] + sorted(list(df_sj[type_col].dropna().unique()))
                    sel_type = st.selectbox("Nach Signal-Typ filtern", unique_types, key="leopold_type_filter")
                else:
                    sel_type = "Alle"
                    st.info("ℹ️ Keine Signal-Typ-Spalte gefunden.")

            with col_f2:
                if adx_col and not df_sj[adx_col].dropna().empty:
                    min_adx, max_adx = float(df_sj[adx_col].min()), float(df_sj[adx_col].max())
                    adx_range = st.slider("ADX Bereich", min_value=min_adx, max_value=max_adx, value=(min_adx, max_adx), key="leopold_adx_slider") if min_adx < max_adx else (min_adx, max_adx)
                else:
                    adx_range = None

            with col_f3:
                if smi_col and not df_sj[smi_col].dropna().empty:
                    min_smi, max_smi = float(df_sj[smi_col].min()), float(df_sj[smi_col].max())
                    smi_range = st.slider("SMI Bereich", min_value=min_smi, max_value=max_smi, value=(min_smi, max_smi), key="leopold_smi_slider") if min_smi < max_smi else (min_smi, max_smi)
                else:
                    smi_range = None

            st.divider()

            # --- FILTER ANWENDEN ---
            df_filtered = df_sj.copy()
            if type_col and sel_type != "Alle":
                df_filtered = df_filtered[df_filtered[type_col] == sel_type]

            if adx_col and adx_range:
                df_filtered = df_filtered[df_filtered[adx_col].between(adx_range[0], adx_range[1]) | df_filtered[adx_col].isna()]

            if smi_col and smi_range:
                df_filtered = df_filtered[df_filtered[smi_col].between(smi_range[0], smi_range[1]) | df_filtered[smi_col].isna()]

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
            perf_elite = safe_mean(df_elite, perf_target_col)
            perf_kauf = safe_mean(df_kauf, perf_target_col)

            win_rate = 0.0
            if not df_filtered.empty and perf_target_col:
                numeric_perf = pd.to_numeric(df_filtered[perf_target_col], errors='coerce')
                winning_trades = (numeric_perf > 0).sum()
                total_valid_trades = numeric_perf.dropna().count()
                if total_valid_trades > 0:
                    win_rate = (winning_trades / total_valid_trades) * 100

            days_col = next((c for c in ["tage_bis_max_perf", "days_to_max", "max_perf_tage", "tage_bis_max"] if c in df_filtered.columns), None)
            avg_days_to_max = safe_mean(df_filtered, days_col)

            # KPI Metriken anzeigen
            st.markdown("### 📊 Performance-Kennzahlen (Gefiltert)")
            r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
            with r1_c1: st.metric("Performance Elite-Signale", f"{perf_elite:+.2f}%")
            with r1_c2: st.metric("Performance Kaufsignale", f"{perf_kauf:+.2f}%")
            with r1_c3: st.metric("Gewinntrades (Quote)", f"{win_rate:.1f}%")
            with r1_c4: st.metric("Ø Tage bis Max-Perf.", f"{avg_days_to_max:.1f} Tage")

            st.divider()

            # --- SWEET-SPOT ANALYSE (ADX & SMI BINS) ---
            if adx_col and smi_col and perf_target_col:
                st.markdown("### 🎯 Indikatoren-Sweet-Spot (ADX & SMI Matrix)")
                st.markdown("Hier siehst du aggregiert, in welchen Bereichen von ADX und SMI die durchschnittliche Performance am höchsten ist.")

                df_heatmap = df_filtered.dropna(subset=[adx_col, smi_col, perf_target_col]).copy()
                if not df_heatmap.empty:
                    # Bins (Intervalle) für ADX und SMI erstellen
                    df_heatmap["ADX_Bin"] = pd.cut(df_heatmap[adx_col], bins=5, precision=0)
                    df_heatmap["SMI_Bin"] = pd.cut(df_heatmap[smi_col], bins=5, precision=0)

                    # Pivot-Tabelle für die Durchschnitts-Performance
                    pivot_perf = df_heatmap.pivot_table(
                        values=perf_target_col, 
                        index="ADX_Bin", 
                        columns="SMI_Bin", 
                        aggfunc="mean"
                    ).reset_index()

                    df_melted = pivot_perf.melt(id_vars="ADX_Bin", var_name="SMI_Bin", value_name="Avg_Performance")
                    df_melted["ADX_Bin"] = df_melted["ADX_Bin"].astype(str)
                    df_melted["SMI_Bin"] = df_melted["SMI_Bin"].astype(str)

                    # Altair Heatmap
                    heatmap = alt.Chart(df_melted).mark_rect().encode(
                        x=alt.X("SMI_Bin:N", title="SMI Bereich"),
                        y=alt.Y("ADX_Bin:N", title="ADX Bereich", sort="descending"),
                        color=alt.Color("Avg_Performance:Q", title="Ø Perf (%)", scale=alt.Scale(scheme="greens")),
                        tooltip=["ADX_Bin", "SMI_Bin", alt.Tooltip("Avg_Performance:Q", format=".2f")]
                    ).properties(height=300)

                    st.altair_chart(heatmap, use_container_width=True)
                else:
                    st.info("Nicht genügend Daten mit validen ADX/SMI-Werten für die Heatmap vorhanden.")

            st.divider()

            # --- TABELLE & DOWNLOAD ---
            st.subheader(f"📋 Gefiltertes Signals Journal ({len(df_filtered)} Einträge)")
            st.dataframe(df_filtered, use_container_width=True, hide_index=True)

            csv_data = df_filtered.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Gefiltertes Signals Journal als CSV herunterladen",
                data=csv_data,
                file_name="signals_journal_filtered_export.csv",
                mime="text/csv",
            )


def render_ui(supabase_client, api_key=None):
    agent = LeopoldAnalyticsManager(supabase_client)
    agent.render_ui(api_key)