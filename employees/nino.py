from supabase import Client
import os
import json
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from db import get_db_client


class NinoSignalsAssistant:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.table_journal = "signals_journal"
        self.table_active_signals = "signals"
        self.table_favorites = "favorites"
        self.table_joris_journal = "joris_journal"
        self.table_trade_journal = "trade_journal"

    def is_valid_ticker(self, ticker):
        """Prüft, ob ein Ticker ein gültiges Börsensymbol ist und keine Platzhalter/Systemnamen."""
        if not ticker or not isinstance(ticker, str):
            return False
        t_upper = ticker.strip().upper()
        # Ungültige Keywords oder Platzhalter ausschließen
        invalid_keywords = ["SYNTHESIS", "AUTO_SWING", "PLACEHOLDER", "TEST"]
        if any(kw in t_upper for kw in invalid_keywords):
            return False
        if len(t_upper) > 15 or " " in t_upper:
            return False
        return True

    def background_routine(self):
        """Ninos autonome Routine: Synct Signale, verarbeitet Metadaten und berechnet 5D/30D für signals_journal & joris_journal."""
        # 0. Favoriten laden
        favorite_tickers = set()
        try:
            fav_res = self.supabase.table(self.table_favorites).select("ticker").execute()
            if fav_res.data:
                favorite_tickers = {
                    row["ticker"].upper() for row in fav_res.data if row.get("ticker")
                }
        except Exception as e:
            print(f"Fehler beim Laden der Favoriten: {e}")

        # Hilfsfunktion zum Extrahieren von Meta-Daten (SMI, ADX, EMA20)
        def parse_meta_data(sig_obj):
            meta_raw = sig_obj.get("meta_data", "{}")
            smi_val, adx_val = None, None
            above_ema = False
            try:
                if isinstance(meta_raw, str):
                    meta_dict = json.loads(meta_raw.replace("'", '"'))
                elif isinstance(meta_raw, dict):
                    meta_dict = meta_raw
                else:
                    meta_dict = {}

                smi_val = meta_dict.get("smi")
                adx_val = meta_dict.get("adx")
                above_ema = bool(meta_dict.get("above_ema20", False))
            except Exception:
                pass
            return (
                float(smi_val) if smi_val is not None else None,
                float(adx_val) if adx_val is not None else None,
                above_ema,
            )

        # 1. Neue Signale in signals_journal synchronisieren
        try:
            active_res = self.supabase.table(self.table_active_signals).select("*").execute()
            active_signals = active_res.data or []

            journal_res = (
                self.supabase.table(self.table_journal)
                .select("ticker, signal_datum")
                .execute()
            )
            journal_data = journal_res.data or []
            existing_set = {
                (str(j["ticker"]).upper(), str(j["signal_datum"])[:10])
                for j in journal_data
                if j and j.get("ticker") and j.get("signal_datum")
            }

            for sig in active_signals:
                if not sig:
                    continue
                ticker = sig.get("ticker")
                if not ticker or not self.is_valid_ticker(ticker):
                    continue

                ticker_upper = ticker.upper()
                sig_date_str = (
                    sig.get("datum")
                    or sig.get("signal_datum")
                    or sig.get("candle_time")
                    or sig.get("created_at")
                )
                if not sig_date_str:
                    continue

                try:
                    sig_date_iso = pd.to_datetime(sig_date_str).strftime("%Y-%m-%d")
                except Exception:
                    continue

                sig_type = sig.get("signal_type") or sig.get("signal_typ", "Standard")
                sig_price = float(sig.get("entry_price") or sig.get("preis") or sig.get("kurs") or 0)

                if (ticker_upper, sig_date_iso) not in existing_set:
                    smi_val, adx_val, above_ema = parse_meta_data(sig)
                    is_fav = ticker_upper in favorite_tickers

                    try:
                        self.supabase.table(self.table_journal).insert({
                            "ticker": ticker_upper,
                            "signal_datum": pd.to_datetime(sig_date_str).isoformat(),
                            "signal_typ": sig_type,
                            "einstiegspreis_zum_signal": sig_price,
                            "smi": smi_val,
                            "adx": adx_val,
                            "is_favorite": is_fav,
                            "above_ema20": above_ema,
                            "status": "Offen (warte auf 5D)",
                        }).execute()
                        existing_set.add((ticker_upper, sig_date_iso))
                    except Exception as insert_err:
                        print(f"Fehler beim Insert ins Journal für {ticker_upper}: {insert_err}")
        except Exception as e:
            print(f"Fehler beim Synchronisieren der Signale: {e}")

        # 2. signals_journal auswerten (5 Tage & 30 Tage)
        try:
            pending_res = (
                self.supabase.table(self.table_journal)
                .select("*")
                .neq("aris_status_30d", True)
                .execute()
            )
            pending_signals = pending_res.data or []
            today = datetime.now().date()

            def process_journal_entries(items, is_joris=False):
                table_name = self.table_joris_journal if is_joris else self.table_journal
                for sig in items:
                    sig_id = sig.get("id")
                    ticker = sig.get("ticker")
                    sig_datum_raw = sig.get("signal_datum") or sig.get("created_at")
                    
                    if not sig_id or not ticker or not sig_datum_raw:
                        continue
                    
                    if not self.is_valid_ticker(ticker):
                        print(f"Überspringe ungültigen Ticker in Journal: {ticker}")
                        continue

                    update_data = {}
                    if sig.get("smi") is None or sig.get("adx") is None:
                        smi_v, adx_v, ema_v = parse_meta_data(sig)
                        if smi_v is not None:
                            update_data["smi"] = smi_v
                        if adx_v is not None:
                            update_data["adx"] = adx_v
                        update_data["above_ema20"] = ema_v

                    sig_date = pd.to_datetime(sig_datum_raw).date()
                    days_passed = (today - sig_date).days
                    base_preis = float(sig.get("einstiegspreis_zum_signal") or sig.get("preis") or sig.get("kurs") or 0)

                    if days_passed >= 5:
                        try:
                            end_date_fetch = sig_date + timedelta(days=45)
                            df_hist = yf.download(
                                ticker,
                                start=sig_date.strftime("%Y-%m-%d"),
                                end=end_date_fetch.strftime("%Y-%m-%d"),
                                progress=False,
                                auto_adjust=True,
                            )

                            if not df_hist.empty:
                                def get_col(df, col_name):
                                    if col_name not in df:
                                        return None
                                    c = df[col_name]
                                    if isinstance(c, pd.DataFrame):
                                        c = c.iloc[:, 0]
                                    return c

                                close_s = get_col(df_hist, "Close")
                                high_s = get_col(df_hist, "High")
                                low_s = get_col(df_hist, "Low")

                                if close_s is not None and not close_s.empty:
                                    if base_preis <= 0:
                                        base_preis = float(close_s.iloc[0])

                                    df_5d = df_hist.head(5)
                                    high_5d_s = get_col(df_5d, "High")
                                    close_5d_s = get_col(df_5d, "Close")

                                    high_5d = float(high_5d_s.max()) if high_5d_s is not None and not high_5d_s.empty else base_preis
                                    close_5d = float(close_5d_s.iloc[-1]) if close_5d_s is not None and not close_5d_s.empty else base_preis

                                    update_data.update({
                                        "max_kurs_5_tage": high_5d,
                                        "max_performance_5_tage": round(((high_5d - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                        "end_kurs_5_tage": close_5d,
                                        "end_performance_5_tage": round(((close_5d - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                        "status": "Ausgewertet (5D)",
                                    })

                                    if days_passed >= 30:
                                        df_30d = df_hist.head(30)
                                        close_30d_s = get_col(df_30d, "Close")
                                        high_30d_s = get_col(df_30d, "High")
                                        low_30d_s = get_col(df_30d, "Low")

                                        end_price_30d = float(close_30d_s.iloc[-1]) if close_30d_s is not None and not close_30d_s.empty else base_preis
                                        max_post_price = float(high_30d_s.max()) if high_30d_s is not None and not high_30d_s.empty else base_preis
                                        min_post_price = float(low_30d_s.min()) if low_30d_s is not None and not low_30d_s.empty else base_preis

                                        update_data.update({
                                            "end_preis_30d": round(end_price_30d, 2),
                                            "max_preis_30d": round(max_post_price, 2),
                                            "min_preis_30d": round(min_post_price, 2),
                                            "max_performance_30d": round(((max_post_price - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                            "min_performance_30d": round(((min_post_price - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                            "performance_30d_end_pct": round(((end_price_30d - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                            "status": "Ausgewertet (30D komplett)",
                                            "aris_status_30d": True
                                        })
                        except Exception as ex:
                            print(f"Fehler bei Auswertung für {ticker}: {ex}")

                    if update_data:
                        self.supabase.table(table_name).update(update_data).eq("id", sig_id).execute()

            process_journal_entries(pending_signals, is_joris=False)

            # 3. joris_journal auswerten
            joris_pending = (
                self.supabase.table(self.table_joris_journal)
                .select("*")
                .neq("aris_status_30d", True)
                .execute()
            )
            process_journal_entries(joris_pending.data or [], is_joris=True)

        except Exception as e:
            print(f"Fehler in background_routine Auswertung: {e}")

    def process_post_exit_tracking(self):
        """Prüft geschlossene Trades im trade_journal und berechnet gestaffelt nach Exit 5D- und 30D-Metriken."""
        try:
            today = datetime.now().date()
            
            res = (
                self.supabase.table(self.table_trade_journal)
                .select("*")
                .eq("status", "Geschlossen")
                .neq("aris_status_30d", True) 
                .execute()
            )
            closed_trades = res.data or []

            def parse_meta_data(sig_obj):
                meta_raw = sig_obj.get("meta_data", "{}")
                smi_val, adx_val = None, None
                above_ema = False
                try:
                    if isinstance(meta_raw, str):
                        meta_dict = json.loads(meta_raw.replace("'", '"'))
                    elif isinstance(meta_raw, dict):
                        meta_dict = meta_raw
                    else:
                        meta_dict = {}
                    smi_val = meta_dict.get("smi")
                    adx_val = meta_dict.get("adx")
                    above_ema = bool(meta_dict.get("above_ema20", False))
                except Exception:
                    pass
                return (
                    float(smi_val) if smi_val is not None else None,
                    float(adx_val) if adx_val is not None else None,
                    above_ema,
                )

            for trade in closed_trades:
                trade_id = trade.get("id")
                ticker = trade.get("ticker")
                exit_date_str = trade.get("ausstieg_datum_zeit") or trade.get("exit_date")
                exit_price = float(trade.get("ausstiegskurs") or trade.get("exit_price", 0))

                if not trade_id or not ticker or not exit_date_str:
                    continue
                
                if not self.is_valid_ticker(ticker):
                    print(f"Überspringe ungültigen Ticker in Trade Journal: {ticker}")
                    continue

                update_data = {}

                if trade.get("smi") is None or trade.get("adx") is None:
                    smi_v, adx_v, ema_v = parse_meta_data(trade)
                    if smi_v is not None:
                        update_data["smi"] = smi_v
                    if adx_v is not None:
                        update_data["adx"] = adx_v
                    update_data["above_ema20"] = ema_v

                exit_date = pd.to_datetime(exit_date_str).date()
                days_passed = (today - exit_date).days

                if days_passed >= 5:
                    try:
                        end_date_fetch = exit_date + timedelta(days=45) 
                        df_post = yf.download(
                            ticker,
                            start=exit_date.strftime("%Y-%m-%d"),
                            end=end_date_fetch.strftime("%Y-%m-%d"),
                            progress=False,
                            auto_adjust=True,
                        )

                        if not df_post.empty:
                            def get_col(df, col_name):
                                if col_name not in df:
                                    return None
                                c = df[col_name]
                                if isinstance(c, pd.DataFrame):
                                    c = c.iloc[:, 0]
                                return c

                            close_series = get_col(df_post, "Close")
                            high_series = get_col(df_post, "High")
                            min_series = get_col(df_post, "Low")

                            if close_series is not None and not close_series.empty:
                                if exit_price <= 0:
                                    exit_price = float(close_series.iloc[0])

                                df_5d = df_post.head(5)
                                high_5d_s = get_col(df_5d, "High")
                                close_5d_s = get_col(df_5d, "Close")

                                high_5d = float(high_5d_s.max()) if high_5d_s is not None and not high_5d_s.empty else exit_price
                                close_5d = float(close_5d_s.iloc[-1]) if close_5d_s is not None and not close_5d_s.empty else exit_price

                                update_data.update({
                                    "max_kurs_5_tage": high_5d,
                                    "max_performance_5_tage": round(((high_5d - exit_price) / exit_price) * 100, 2) if exit_price > 0 else 0,
                                    "end_kurs_5_tage": close_5d,
                                    "end_performance_5_tage": round(((close_5d - exit_price) / exit_price) * 100, 2) if exit_price > 0 else 0,
                                    "status": "Geschlossen (5D ausgewertet)",
                                })

                                if days_passed >= 30:
                                    df_30d = df_post.head(30)
                                    close_30d_s = get_col(df_30d, "Close")
                                    high_30d_s = get_col(df_30d, "High")
                                    low_30d_s = get_col(df_30d, "Low")

                                    end_price_30d = float(close_30d_s.iloc[-1]) if close_30d_s is not None and not close_30d_s.empty else exit_price
                                    max_post_price = float(high_30d_s.max()) if high_30d_s is not None and not high_30d_s.empty else exit_price
                                    min_post_price = float(low_30d_s.min()) if low_30d_s is not None and not low_30d_s.empty else exit_price

                                    perf_after_end = ((end_price_30d - exit_price) / exit_price) * 100 if exit_price > 0 else 0
                                    perf_after_max = ((max_post_price - exit_price) / exit_price) * 100 if exit_price > 0 else 0
                                    drawdown_after = ((min_post_price - exit_price) / exit_price) * 100 if exit_price > 0 else 0

                                    update_data.update({
                                        "end_preis_30d": round(end_price_30d, 2),
                                        "max_preis_30d": round(max_post_price, 2),
                                        "min_preis_30d": round(min_post_price, 2),
                                        "max_performance_30d": round(perf_after_max, 2),
                                        "min_performance_30d": round(drawdown_after, 2),
                                        "performance_30d_end_pct": round(perf_after_end, 2),
                                        "status": "Geschlossen (30D komplett)",
                                        "aris_status_30d": True
                                    })
                    except Exception as e:
                        print(f"Fehler beim Post-Exit-Tracking für {ticker}: {e}")

                if update_data:
                    self.supabase.table(self.table_trade_journal).update(update_data).eq("id", trade_id).execute()

        except Exception as e:
            print(f"Fehler in process_post_exit_tracking: {e}")

    def get_signals_history(self):
        try:
            res = (
                self.supabase.table(self.table_journal)
                .select("*")
                .order("signal_datum", desc=True)
                .execute()
            )
            return res.data if res.data else []
        except Exception:
            return []

    def get_joris_journal_history(self):
        try:
            res = (
                self.supabase.table(self.table_joris_journal)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            return res.data if res.data else []
        except Exception:
            return []


if __name__ == "__main__":
    supabase_client = get_db_client()
    nino = NinoSignalsAssistant(supabase_client)

    print("Nino startet Hintergrund-Routinen (Signale & Joris Journal)...")
    nino.background_routine()

    print("Nino startet Post-Exit-Tracking (5D/30D Tracking für Trade Journal)...")
    nino.process_post_exit_tracking()

    print("Nino Routinen erfolgreich beendet.")