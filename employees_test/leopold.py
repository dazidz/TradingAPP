from datetime import datetime, timedelta
import pandas as pd
import json
import io
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
        st.markdown("Interaktive Streudiagramm-Analyse (ADX vs. SMI), Timing-Optimierung & Filterung des `signals_journal` (basierend auf Max-Performance / MFE).")
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

            # Spalten-Erkennung absichern (Max-Performance hat jetzt Priorität!)
            possible_type_cols = ["signal_typ", "typ", "signal_type", "type"]
            type_col = next((c for c in possible_type_cols if c in df_sj.columns), None)

            adx_col = next((c for c in ["adx", "average_directional_index", "adx_value"] if c in df_sj.columns), None)
            smi_col = next((c for c in ["smi", "stochastic_momentum_index", "smi_value"] if c in df_sj.columns), None)
            
            # WICHTIG: Max-Performance (MFE) als primäre Zielgröße für Leopold
            perf_target_col = next((c for c in ["max_performance_5_tage", "mfe", "max_performance", "end_performance_5_tage", "performance"] if c in df_sj.columns), None)

            if type_col:
                df_sj[type_col] = df_sj[type_col].astype(str).str.strip()

            if adx_col:
                df_sj[adx_col] = pd.to_numeric(df_sj[adx_col], errors="coerce")
            if smi_col:
                df_sj[smi_col] = pd.to_numeric(df_sj[smi_col], errors="coerce")
            if perf_target_col:
                df_sj[perf_target_col] = pd.to_numeric(df_sj[perf_target_col], errors="coerce")

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

            st.divider()

            # --- INTERAKTIVES ALTAIR-STREUDIAGRAMM (ADX vs. SMI - Gefärbt nach Max-Performance) ---
            if adx_col and smi_col and perf_target_col and not df_base.empty:
                st.markdown("### 🎯 ADX vs. SMI Streudiagramm (Eingefärbt nach Max-Performance / MFE)")
                st.markdown("Jeder Punkt repräsentiert einen Trade. Die Farbe zeigt die maximale Intraday/5-Tage-Performance (Grün = starker Peak, Rot = schlechter Verlauf).")

                df_scatter = df_base.dropna(subset=[adx_col, smi_col, perf_target_col]).copy()
                
                if not df_scatter.empty:
                    tooltip_fields = ["ticker" if "ticker" in df_scatter.columns else None, type_col if type_col in df_scatter.columns else None]
                    tooltip_fields = [t for t in tooltip_fields if t is not None]
                    
                    tooltip_fields.extend([
                        alt.Tooltip(f"{adx_col}:Q", format=".1f", title="ADX"),
                        alt.Tooltip(f"{smi_col}:Q", format=".2f", title="SMI"),
                        alt.Tooltip(f"{perf_target_col}:Q", format=".2f", title="Max. Perf. (%)")
                    ])

                    scatter_chart = alt.Chart(df_scatter).mark_circle(size=80, opacity=0.85).encode(
                        x=alt.X(f"{adx_col}:Q", title="ADX (Trendstärke)"),
                        y=alt.Y(f"{smi_col}:Q", title="SMI (Momentum)"),
                        color=alt.Color(
                            f"{perf_target_col}:Q", 
                            title="Max. Perf. (%)", 
                            scale=alt.Scale(scheme="redyellowgreen", domainMid=0)
                        ),
                        tooltip=tooltip_fields
                    ).interactive().properties(height=420)

                    st.altair_chart(scatter_chart, use_container_width=True)
                else:
                    st.info("Nicht genügend gültige Datenpunkte für das Streudiagramm vorhanden.")
            else:
                st.warning("Für das Streudiagramm werden gültige ADX-, SMI- und Performance-Spalten benötigt.")

            st.divider()

            # --- KPI METRIKEN (Basiert auf Max-Performance) ---
            def safe_mean(dataframe, column_name):
                if not dataframe.empty and column_name in dataframe.columns:
                    val = pd.to_numeric(dataframe[column_name], errors='coerce').mean()
                    return val if pd.notnull(val) else 0.0
                return 0.0

            drawdown_col = next((c for c in ["max_drawdown", "mae", "drawdown"] if c in df_sj.columns), None)
            days_col = next((c for c in ["tage_bis_max_perf", "days_to_max", "max_perf_tage", "tage_bis_max"] if c in df_base.columns), None)

            win_rate = 0.0
            if not df_base.empty and perf_target_col:
                numeric_perf = pd.to_numeric(df_base[perf_target_col], errors='coerce')
                winning_trades = (numeric_perf > 0).sum()
                total_valid_trades = numeric_perf.dropna().count()
                if total_valid_trades > 0:
                    win_rate = (winning_trades / total_valid_trades) * 100

            avg_days_to_max = safe_mean(df_base, days_col)
            avg_max_perf = safe_mean(df_base, perf_target_col)
            avg_drawdown = safe_mean(df_base, drawdown_col)

            st.markdown(f"### 📊 Gesamt-Kennzahlen (Basiert auf Max-Performance / {len(df_base)} Trades)")
            r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
            with r1_c1: st.metric("Win-Rate (Max > 0%)", f"{win_rate:.1f}%")
            with r1_c2: st.metric("Ø Max. Performance (MFE)", f"{avg_max_perf:+.2f}%")
            with r1_c3: st.metric("Ø Max. Drawdown (MAE)", f"{avg_drawdown:+.2f}%")
            with r1_c4: st.metric("Ø Tage bis Peak-Perf.", f"{avg_days_to_max:.1f} Tage")

            st.divider()

            # --- TABELLE & ECHTER EXCEL-DOWNLOAD (.xlsx) ---
            st.subheader(f"📋 Signals Journal ({len(df_base)} Einträge)")
            st.dataframe(df_base, use_container_width=True, hide_index=True)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_base.to_excel(writer, index=False, sheet_name='Signals Journal')
            excel_data = output.getvalue()

            st.download_button(
                label="📥 Signals Journal als echte Excel-Datei (.xlsx) herunterladen",
                data=excel_data,
                file_name="signals_journal_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


def render_ui(supabase_client, api_key=None):
    agent = LeopoldAnalyticsManager(supabase_client)
    agent.render_ui(api_key)