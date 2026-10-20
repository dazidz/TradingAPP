from datetime import datetime, timedelta
import os
import json
import math
import pandas as pd
import yfinance as yf
import streamlit as st
from db import get_db_client

AGENT_TITLE = "Nino"

class NinoSignalsAssistant:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.table_active_signals = "signals"
        self.table_signals_journal = "signals_journal"
        self.table_joris_journal = "joris_journal"
        self.table_aris_arbeitsspeicher = "aris_arbeitsspeicher"
        self.table_favorites = "favorites"

        try:
            test_res = self.supabase.table(self.table_active_signals).select("*", count="exact").limit(1).execute()
            print(f"✅ Supabase Verbindung erfolgreich! Tabelle '{self.table_active_signals}' erreichbar.")
        except Exception as e:
            print(f"❌ SUPABASE VERBINDUNGS-FEHLER: {e}")

    def is_valid_ticker(self, ticker):
        """Prüft, ob ein Ticker ein gültiges Börsensymbol ist und keine Platzhalter/Systemnamen."""
        if not ticker or not isinstance(ticker, str):
            return False
        t_upper = ticker.strip().upper()
        invalid_keywords = ["SYNTHESIS", "AUTO_SWING", "PLACEHOLDER", "TEST"]
        if any(kw in t_upper for kw in invalid_keywords):
            return False
        if len(t_upper) > 15 or " " in t_upper:
            return False
        return True

    def _clean_ticker_for_yf(self, ticker):
        """Bereinigt typische Formatierungsfehler für yfinance (z.B. angehängte Nullen wie .L0 -> .L)."""
        t = ticker.strip().upper()
        if t.endswith(".L0"):
            t = t[:-1]
        return t

    def _safe_float(self, val, default=0.0):
        if val is None:
            return default
        if isinstance(val, bool):
            return float(val)
        try:
            val_str = str(val).strip().lower()
            if "true" in val_str or "false" in val_str or len(val_str) > 20:
                return default
            res = float(val)
            if math.isnan(res) or math.isinf(res):
                return default
            return res
        except (ValueError, TypeError):
            return default

    def _safe_bool(self, val, default=False):
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        val_str = str(val).strip().lower()
        if val_str in ["true", "1", "t", "yes", "y"]:
            return True
        if val_str in ["false", "0", "f", "no", "n"]:
            return False
        if "true" in val_str and "false" not in val_str:
            return True
        return default

    def _get_favorite_tickers(self):
        favorite_tickers = set()
        try:
            fav_res = self.supabase.table(self.table_favorites).select("ticker").execute()
            if fav_res.data:
                favorite_tickers = {row["ticker"].upper() for row in fav_res.data if row.get("ticker")}
        except Exception as e:
            print(f"Fehler beim Laden der Favoriten: {e}")
        return favorite_tickers

    def _parse_meta_data(self, sig_obj):
        meta_raw = sig_obj.get("meta_data", "{}")
        smi_val, adx_val = None, None
        above_ema = False
        try:
            if isinstance(meta_raw, str) and meta_raw.strip():
                clean_meta = meta_raw.replace("'", '"')
                meta_dict = json.loads(clean_meta)
            elif isinstance(meta_raw, dict):
                meta_dict = meta_raw
            else:
                meta_dict = {}

            smi_raw = meta_dict.get("smi")
            adx_raw = meta_dict.get("adx")
            
            smi_val = self._safe_float(smi_raw, default=None) if smi_raw is not None else None
            adx_val = self._safe_float(adx_raw, default=None) if adx_raw is not None else None
            above_ema = self._safe_bool(meta_dict.get("above_ema20", False))
        except Exception:
            pass
        return smi_val, adx_val, above_ema

    def _fetch_5d_performance(self, ticker, sig_date, base_preis):
        clean_ticker = self._clean_ticker_for_yf(ticker)
        try:
            end_date_fetch = sig_date + timedelta(days=20)
            df_hist = yf.download(
                clean_ticker,
                start=sig_date.strftime("%Y-%m-%d"),
                end=end_date_fetch.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )

            if df_hist.empty or len(df_hist) < 2:
                return None

            def get_col(df, col_name):
                if col_name not in df:
                    return None
                c = df[col_name]
                if isinstance(c, pd.DataFrame):
                    c = c.iloc[:, 0]
                return c

            close_s = get_col(df_hist, "Close")
            high_s = get_col(df_hist, "High")

            if close_s is None or close_s.empty or high_s is None or high_s.empty:
                return None

            if base_preis <= 0:
                base_preis = self._safe_float(close_s.iloc[0], default=1.0)

            df_5d = df_hist.iloc[1:6] if len(df_hist) >= 6 else df_hist.iloc[1:]
            if df_5d.empty:
                return None

            high_5d_s = get_col(df_5d, "High")
            close_5d_s = get_col(df_5d, "Close")

            high_5d = self._safe_float(high_5d_s.max(), default=base_preis) if high_5d_s is not None and not high_5d_s.empty else base_preis
            close_5d = self._safe_float(close_5d_s.iloc[-1], default=base_preis) if close_5d_s is not None and not close_5d_s.empty else base_preis

            candle_time_max = None
            if high_5d_s is not None and not high_5d_s.empty:
                max_idx = high_5d_s.idxmax()
                if pd.notnull(max_idx):
                    candle_time_max = pd.to_datetime(max_idx).isoformat()

            max_perf_5d = round(((high_5d - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0
            end_perf_5d = round(((close_5d - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0

            return {
                "base_preis": base_preis,
                "max_performance_5_tage": self._safe_float(max_perf_5d, 0.0),
                "candle_time_max_5_tage": candle_time_max,
                "end_performance_5_tage": self._safe_float(end_perf_5d, 0.0),
            }
        except Exception as e:
            print(f"Fehler bei yfinance Download für {clean_ticker}: {e}")
            return None

    def process_signals_to_journal(self):
        print("Nino verarbeitet aktive Signale (signals -> signals_journal -> aris_arbeitsspeicher)...")

        try:
            today = datetime.now().date()
            favorite_tickers = self._get_favorite_tickers()

            active_res = self.supabase.table(self.table_active_signals).select("*").execute()
            active_signals = active_res.data or []
            print(f"Gefundene aktive Signale in DB: {len(active_signals)}")

            if not active_signals:
                return

            for sig in active_signals:
                try:
                    if not sig:
                        continue
                    ticker = sig.get("ticker")
                    if not ticker or not self.is_valid_ticker(ticker):
                        continue

                    ticker_upper = ticker.upper()
                    company_name = sig.get("company_name") or ticker_upper

                    sig_date_str = sig.get("candle_time") or sig.get("datum") or sig.get("signal_datum") or sig.get("created_at")
                    if not sig_date_str:
                        continue

                    sig_date = pd.to_datetime(sig_date_str).date()
                    days_passed = (today - sig_date).days
                    if days_passed < 5:
                        print(f"