from datetime import datetime, timedelta
import json
import os
from db import get_db_client
import pandas as pd
import yfinance as yf


class NinoSignalsAssistant:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.table_active_signals = "signals"
        self.table_signals_journal = "signals_journal"
        self.table_joris_journal = "joris_journal"
        self.table_aris_arbeitsspeicher = "aris_arbeitsspeicher"
        self.table_favorites = "favorites"

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
        """Wandelt Werte sicher in Float um und fängt kaputte Strings/Booleans ab."""
        if val is None:
            return default
        if isinstance(val, bool):
            return float(val)
        try:
            val_str = str(val).strip().lower()
            if "true" in val_str or "false" in val_str or len(val_str) > 20:
                # Fängt verklebte Strings wie 'falsetrue' ab
                return default
            return float(val)
        except (ValueError, TypeError):
            return default

    def _safe_bool(self, val, default=False):
        """Wandelt Werte sicher in Boolean um und fängt kaputte verklebte Strings ab."""
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        val_str = str(val).strip().lower()
        if val_str in ["true", "1", "t", "yes", "y"]:
            return True
        if val_str in ["false", "0", "f", "no", "n"]:
            return False
        # Falls Supabase hier Schrott wie 'falsetrue' liefert, fangen wir es ab:
        if "true" in val_str and "false" not in val_str:
            return True
        return default

    def _get_favorite_tickers(self):
        """Lädt alle Favoriten-Ticker aus der Datenbank."""
        favorite_tickers = set()
        try:
            fav_res = (
                self.supabase.table(self.table_favorites).select("ticker").execute()
            )
            if fav_res.data:
                favorite_tickers = {
                    row["ticker"].upper() for row in fav_res.data if row.get("ticker")
                }
        except Exception as e:
            print(f"Fehler beim Laden der Favoriten: {e}")
        return favorite_tickers

    def _parse_meta_data(self, sig_obj):
        """Extrahiert Meta-Daten wie SMI, ADX und EMA20 extrem robust."""
        meta_raw = sig_obj.get("meta_data", "{}")
        smi_val, adx_val = None, None
        above_ema = False
        try:
            if isinstance(meta_raw, str) and meta_raw.strip():
                # Falls meta_raw ein kaputter String ist, der kein echtes JSON ist
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
        except Exception as e:
            # Fallback falls json.loads wegen kaputter Strings fehlschlägt
            pass
        return smi_val, adx_val, above_ema

    def _fetch_5d_performance(self, ticker, sig_date, base_preis):
        """Zieht über yfinance die Kursdaten ab sig_date und berechnet 5-Tage Max- & End-Performance."""
        clean_ticker = self._clean_ticker_for_yf(ticker)
        try:
            end_date_fetch = sig_date + timedelta(days=15)
            df_hist = yf.download(
                clean_ticker,
                start=sig_date.strftime("%Y-%m-%d"),
                end=end_date_fetch.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )

            if df_hist.empty:
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

            if close_s is None or close_s.empty:
                return None

            if base_preis <= 0:
                base_preis = self._safe_float(close_s.iloc[0], default=1.0)

            df_5d = df_hist.head(5)
            high_5d_s = get_col(df_5d, "High")
            close_5d_s = get_col(df_5d, "Close")

            high_5d = (
                self._safe_float(high_5d_s.max(), default=base_preis)
                if high_5d_s is not None and not high_5d_s.empty
                else base_preis
            )
            close_5d = (
                self._safe_float(close_5d_s.iloc[-1], default=base_preis)
                if close_5d_s is not None and not close_5d_s.empty
                else base_preis
            )

            candle_time_max = None
            if high_5d_s is not None and not high_5d_s.empty:
                max_idx = high_5d_s.idxmax()
                if pd.notnull(max_idx):
                    candle_time_max = pd.to_datetime(max_idx).isoformat()

            max_perf_5d = (
                round(((high_5d - base_preis) / base_preis) * 100, 2)
                if base_preis > 0
                else 0
            )
            end_perf_5d = (
                round(((close_5d - base_preis) / base_preis) * 100, 2)
                if base_preis > 0
                else 0
            )

            return {
                "base_preis": base_preis,
                "max_kurs_5_tage": high_5d,
                "max_performance_5_tage": max_perf_5d,
                "candle_time_max_5_tage": candle_time_max,
                "end_kurs_5_tage": close_5d,
                "end_performance_5_tage": end_perf_5d,
            }
        except Exception as e:
            print(f"Fehler bei yfinance Download für {clean_ticker}: {e}")
            return None

    def process_signals_to_journal(self):
        print(
            "Nino verarbeitet aktive Signale (signals -> signals_journal ->"
            " aris_arbeitsspeicher)..."
        )
        try:
            today = datetime.now().date()
            favorite_tickers = self._get_favorite_tickers()

            active_res = (
                self.supabase.table(self.table_active_signals).select("*").execute()
            )
            active_signals = active_res.data or []
            print(f"Gefundene aktive Signale in DB: {len(active_signals)}")

            if not active_signals:
                return

            for sig in active_signals:
                if not sig:
                    continue
                ticker = sig.get("ticker")
                if not ticker or not self.is_valid_ticker(ticker):
                    continue

                ticker_upper = ticker.upper()
                sig_date_str = (
                    sig.get("candle_time")
                    or sig.get("datum")
                    or sig.get("signal_datum")
                    or sig.get("created_at")
                )
                if not sig_date_str:
                    continue

                try:
                    sig_date = pd.to_datetime(sig_date_str).date()
                except Exception:
                    continue

                days_passed = (today - sig_date).days
                if days_passed < 5:
                    continue

                sig_type = (
                    sig.get("signal_type")
                    or sig.get("signal_typ")
                    or sig.get("typ")
                    or None
                )
                
                sig_price_raw = (
                    sig.get("entry_price")
                    or sig.get("preis")
                    or sig.get("kurs")
                    or sig.get("einstiegspreis")
                    or 0
                )
                sig_price = self._safe_float(sig_price_raw, default=0.0)
                
                smi_val, adx_val, above_ema = self._parse_meta_data(sig)
                is_fav = ticker_upper in favorite_tickers

                perf_data = self._fetch_5d_performance(
                    ticker_upper, sig_date, sig_price
                )
                if not perf_data:
                    continue

                journal_entry = {
                    "ticker": ticker_upper,
                    "candle_time": pd.to_datetime(sig_date_str).isoformat(),
                    "signal_typ": sig_type,
                    "status": True,
                    "smi": smi_val,
                    "adx": adx_val,
                    "is_favorite": is_fav,
                    "above_ema20": above_ema,
                    "max_kurs_5_tage": perf_data["max_kurs_5_tage"],
                    "max_performance_5_tage": perf_data["max_performance_5_tage"],
                    "candle_time_max_5_tage": perf_data.get("candle_time_max_5_tage"),
                    "end_kurs_5_tage": perf_data["end_kurs_5_tage"],
                    "end_performance_5_tage": perf_data["end_performance_5_tage"],
                }

                self.supabase.table(self.table_signals_journal).insert(
                    journal_entry
                ).execute()

                arbeitsspeicher_entry = {
                    "ticker": ticker_upper,
                    "candle_time": pd.to_datetime(sig_date_str).isoformat(),
                    "signal_typ": sig_type,
                    "smi": smi_val,
                    "adx": adx_val,
                    "is_favorite": is_fav,
                    "above_ema20": above_ema,
                    "end_performance_5_tage": perf_data["end_performance_5_tage"],
                    "quelle": "signals_journal",
                }
                self.supabase.table(self.table_aris_arbeitsspeicher).insert(
                    arbeitsspeicher_entry
                ).execute()

                sig_id = sig.get("id")
                if sig_id:
                    self.supabase.table(self.table_active_signals).delete().eq(
                        "id", sig_id
                    ).execute()

                print(
                    f"✅ Signal für {ticker_upper} erfolgreich ausgewertet und übergeben."
                )

        except Exception as e:
            print(f"❌ Fehler in process_signals_to_journal: {e}")

    def process_joris_journal(self):
        print("Nino verarbeitet joris_journal...")
        try:
            today = datetime.now().date()
            
            joris_res = (
                self.supabase.table(self.table_joris_journal)
                .select("*")
                .is_("status", "null")
                .execute()
            )
            joris_items = joris_res.data or []
            print(f"Gefundene unbearbeitete Joris-Signale: {len(joris_items)}")

            for item in joris_items:
                ticker = item.get("ticker")
                if not ticker or not self.is_valid_ticker(ticker):
                    continue

                ticker_upper = ticker.upper()
                date_str = (
                    item.get("candle_time")
                    or item.get("signal_datum")
                    or item.get("created_at")
                )
                if not date_str:
                    continue

                try:
                    sig_date = pd.to_datetime(date_str).date()
                except Exception:
                    continue

                days_passed = (today - sig_date).days
                if days_passed < 5:
                    continue

                base_price_raw = (
                    item.get("preis")
                    or item.get("kurs")
                    or item.get("einstiegspreis_zum_signal")
                    or 0
                )
                base_price = self._safe_float(base_price_raw, default=0.0)

                perf_data = self._fetch_5d_performance(
                    ticker_upper, sig_date, base_price
                )
                if not perf_data:
                    continue

                sig_type = (
                    item.get("signal_type")
                    or item.get("signal_typ")
                    or item.get("typ")
                    or None
                )
                smi_val, adx_val, above_ema = self._parse_meta_data(item)

                updated_joris_data = {
                    "status": True,
                    "max_kurs_5_tage": perf_data["max_kurs_5_tage"],
                    "max_performance_5_tage": perf_data["max_performance_5_tage"],
                    "candle_time_max_5_tage": perf_data.get("candle_time_max_5_tage"),
                    "end_kurs_5_tage": perf_data["end_kurs_5_tage"],
                    "end_performance_5_tage": perf_data["end_performance_5_tage"],
                }

                item_id = item.get("id")
                if item_id:
                    self.supabase.table(self.table_joris_journal).update(
                        updated_joris_data
                    ).eq("id", item_id).execute()

                arbeitsspeicher_entry = {
                    "ticker": ticker_upper,
                    "candle_time": pd.to_datetime(date_str).isoformat(),
                    "signal_typ": sig_type,
                    "smi": smi_val,
                    "adx": adx_val,
                    "above_ema20": above_ema,
                    "end_performance_5_tage": perf_data["end_performance_5_tage"],
                    "quelle": "joris_journal",
                }

                self.supabase.table(self.table_aris_arbeitsspeicher).insert(
                    arbeitsspeicher_entry
                ).execute()
                print(f"✅ Joris-Journal Eintrag für {ticker_upper} übergeben und als erledigt markiert.")

        except Exception as e:
            print(f"❌ Fehler in process_joris_journal: {e}")

    def process_top_flop_list(self):
        print("Nino verarbeitet Top 5 Watchlist...")
        try:
            today = datetime.now().date()
            today_iso = today.strftime("%Y-%m-%d")

            res = self.supabase.table("watchlist").select("*").execute()
            watchlist_items = res.data or []

            performance_results = []
            for item in watchlist_items:
                if not item or not item.get("ticker"):
                    continue
                ticker = item["ticker"].upper()
                if not self.is_valid_ticker(ticker):
                    continue

                try:
                    clean_ticker = self._clean_ticker_for_yf(ticker)
                    start_fetch = today - timedelta(days=10)
                    df_hist = yf.download(
                        clean_ticker,
                        start=start_fetch.strftime("%Y-%m-%d"),
                        end=today.strftime("%Y-%m-%d"),
                        progress=False,
                        auto_adjust=True,
                    )

                    if df_hist.empty or len(df_hist) < 2:
                        continue

                    def get_col(df, col_name):
                        if col_name not in df:
                            return None
                        c = df[col_name]
                        if isinstance(c, pd.DataFrame):
                            c = c.iloc[:, 0]
                        return c

                    df_5d = df_hist.tail(5)
                    close_s = get_col(df_5d, "Close")
                    
                    if close_s is None or close_s.empty:
                        continue

                    base_kurs = self._safe_float(close_s.iloc[0], default=1.0)
                    end_kurs = self._safe_float(close_s.iloc[-1], default=base_kurs)
                    perf = (
                        round(((end_kurs - base_kurs) / base_kurs) * 100, 2)
                        if base_kurs > 0
                        else 0
                    )

                    smi_val, adx_val, above_ema = self._parse_meta_data(item)

                    performance_results.append({
                        "ticker": ticker,
                        "signal_typ": None,
                        "smi": smi_val,
                        "adx": adx_val,
                        "end_performance_5_tage": perf,
                        "end_kurs_5_tage": end_kurs,
                        "candle_time": datetime.now().isoformat(),
                    })
                except Exception as e:
                    print(f"Warnung bei Watchlist-Ticker {ticker}: {e}")

            if not performance_results:
                return

            performance_results.sort(
                key=lambda x: self._safe_float(x.get("end_performance_5_tage", 0)), reverse=True
            )
            top_5 = performance_results[:5]

            for entry in top_5:
                ticker = entry.get("ticker")
                perf = entry.get("end_performance_5_tage")

                payload = {
                    "datum": today_iso,
                    "kategorie": "TOP",
                    "ticker": ticker,
                    "signal_typ": None,
                    "performance": perf,
                    "end_kurs": entry.get("end_kurs_5_tage"),
                    "quelle": "top_flop_watchlist",
                }
                self.supabase.table("top_flop_journal").insert(payload).execute()

                arbeitsspeicher_entry = {
                    "ticker": ticker,
                    "candle_time": entry.get("candle_time"),
                    "signal_typ": None,
                    "smi": entry.get("smi"),
                    "adx": entry.get("adx"),
                    "end_performance_5_tage": perf,
                    "quelle": "top_flop_watchlist",
                }
                self.supabase.table(self.table_aris_arbeitsspeicher).insert(
                    arbeitsspeicher_entry
                ).execute()

            print("✅ Top 5 Watchlist verarbeitet und gespeichert.")

        except Exception as e:
            print(f"❌ Fehler in process_top_flop_list: {e}")

    def run_all(self):
        self.process_signals_to_journal()
        self.process_joris_journal()
        self.process_top_flop_list()


if __name__ == "__main__":
    supabase_client = get_db_client()
    nino = NinoSignalsAssistant(supabase_client)
    nino.run_all()