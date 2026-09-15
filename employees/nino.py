from supabase import Client
import os
import json
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from db import get_db_client


class NinoSignalsAssistant:

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.table_journal = "signals_journal"
        self.table_active_signals = "signals"
        self.table_favorites = "favorites"
        self.table_joris_journal = "joris_journal"
        self.table_trade_journal = "trade_journal"

    def background_routine(self):
        """Ninos autonome Routine: Synct Signale, verarbeitet Metadaten (SMI, ADX, EMA20) 
        und berechnet 5-Tages- sowie 30-Tage-Metriken.
        """
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

        # 1. Neue Signale in signals_journal synchronisieren (mit robustem Einzelsatz-Catch)
        try:
            active_res = self.supabase.table(self.table_active_signals).select("*").execute()
            active_signals = active_res.data or []
            print(f"Nino hat {len(active_signals)} aktive Signale in '{self.table_active_signals}' gefunden.")

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

            new_count = 0
            for sig in active_signals:
                if not sig:
                    continue
                ticker = sig.get("ticker")
                if not ticker:
                    continue

                ticker_upper = ticker.upper()
                sig_date_str = (
                    sig.get("datum")
                    or sig.get("signal_datum")
                    or sig.get("candle_time")
                    or sig.get("created_at")
                )
                
                if not sig_date_str:
                    print(f"Überspringe {ticker_upper}: Kein Datum gefunden im Signal.")
                    continue

                try:
                    sig_date_iso = pd.to_datetime(sig_date_str).strftime("%Y-%m-%d")
                except Exception as date_err:
                    print(f"Fehler beim Parsen des Datums '{sig_date_str}' für {ticker_upper}: {date_err}")
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
                        new_count += 1
                        print(f"Neues Signal erfolgreich synchronisiert: {ticker_upper} vom {sig_date_iso}")
                    except Exception as insert_err:
                        print(f"Fehler beim Insert ins Journal für {ticker_upper}: {insert_err}")
                        
            print(f"Synchronisation beendet. {new_count} neue Signale hinzugefügt.")
        except Exception as e:
            print(f"Fehler beim Synchronisieren der Signale: {e}")

        # 2. signals_journal auswerten (5 Tage & vollständiges 30-Tage-Min/Max-Tracking)
        try:
            pending_res = (
                self.supabase.table(self.table_journal)
                .select("*")
                .neq("aris_status_30d", True)
                .execute()
            )
            pending_signals = pending_res.data or []
            today = datetime.now().date()

            for sig in pending_signals:
                sig_id = sig.get("id")
                ticker = sig.get("ticker")
                sig_datum_raw = sig.get("signal_datum") or sig.get("created_at")
                if not sig_id or not ticker or not sig_datum_raw:
                    continue

                sig_date = pd.to_datetime(sig_datum_raw).date()
                days_passed = (today - sig_date).days
                base_preis = float(sig.get("einstiegspreis_zum_signal", 0))

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
                            update_data = {}
                            
                            if base_preis <= 0 and "Close" in df_hist:
                                first_close = df_hist["Close"].iloc[:, 0] if isinstance(df_hist["Close"], pd.DataFrame) else df_hist["Close"]
                                base_preis = float(first_close.iloc[0])

                            if len(df_hist) >= 5:
                                df_5d = df_hist.head(5)
                                high_5d = (df_5d["High"].iloc[:, 0] if isinstance(df_5d["High"], pd.DataFrame) else df_5d["High"]).max()
                                close_5d = (df_5d["Close"].iloc[:, 0] if isinstance(df_5d["Close"], pd.DataFrame) else df_5d["Close"]).iloc[-1]
                                
                                update_data.update({
                                    "max_kurs_5_tage": float(high_5d),
                                    "max_performance_5_tage": round(((float(high_5d) - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                    "end_kurs_5_tage": float(close_5d),
                                    "end_performance_5_tage": round(((float(close_5d) - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                    "status": "Ausgewertet (5D)",
                                })

                            if days_passed >= 30 and len(df_hist) >= 10:
                                df_30d = df_hist.head(30)
                                close_30d = (df_30d["Close"].iloc[:, 0] if isinstance(df_30d["Close"], pd.DataFrame) else df_30d["Close"])
                                high_30d = (df_30d["High"].iloc[:, 0] if isinstance(df_30d["High"], pd.DataFrame) else df_30d["High"])
                                low_30d = (df_30d["Low"].iloc[:, 0] if isinstance(df_30d["Low"], pd.DataFrame) else df_30d["Low"])

                                end_price_30d = float(close_30d.iloc[-1])
                                max_post_price = float(high_30d.max())
                                min_post_price = float(low_30d.min())

                                update_data.update({
                                    "end_preis_30d": round(end_price_30d, 2),
                                    "max_preis_30d": round(max_post_price, 2),
                                    "min_preis_30d": round(min_post_price, 2),
                                    "max_performance_30d": round(((max_post_price - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                    "min_performance_30d": round(((min_post_price - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                    "performance_30d_end_pct": round(((end_price_30d - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                    "status": "Ausgewertet (30D komplett)",
                                })

                            if update_data:
                                self.supabase.table(self.table_journal).update(update_data).eq(
                                    "id", sig_id
                                ).execute()
                    except Exception as e:
                        print(f"Fehler bei Signal-ID {sig_id} ({ticker}): {e}")
        except Exception as e:
            print(f"Fehler in signals_journal Auswertung: {e}")

        # 3. joris_journal auswerten (inkl. einmaligem Einlesen von SMI, ADX, EMA20 aus meta_data falls leer)
        try:
            joris_pending = (
                self.supabase.table(self.table_joris_journal)
                .select("*")
                .neq("aris_status_30d", True)
                .execute()
            )
            joris_items = joris_pending.data or []
            today = datetime.now().date()

            for sig in joris_items:
                sig_id = sig.get("id")
                ticker = sig.get("ticker")
                sig_datum_raw = sig.get("created_at") or sig.get("signal_datum")
                if not sig_id or not ticker or not sig_datum_raw:
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
                            close_col = df_hist["Close"].iloc[:, 0] if isinstance(df_hist["Close"], pd.DataFrame) else df_hist["Close"]
                            base_preis = float(close_col.iloc[0])

                            if len(df_hist) >= 5:
                                df_5d = df_hist.head(5)
                                high_5d = (df_5d["High"].iloc[:, 0] if isinstance(df_5d["High"], pd.DataFrame) else df_5d["High"]).max()
                                close_5d = (df_5d["Close"].iloc[:, 0] if isinstance(df_5d["Close"], pd.DataFrame) else df_5d["Close"]).iloc[-1]
                                
                                update_data.update({
                                    "max_kurs_5_tage": float(high_5d),
                                    "max_performance_5_tage": round(((float(high_5d) - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                    "end_kurs_5_tage": float(close_5d),
                                    "end_performance_5_tage": round(((float(close_5d) - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                    "status": "Ausgewertet (5D)",
                                })

                            if days_passed >= 30 and len(df_hist) >= 10:
                                df_30d = df_hist.head(30)
                                close_30d = (df_30d["Close"].iloc[:, 0] if isinstance(df_30d["Close"], pd.DataFrame) else df_30d["Close"])
                                high_30d = (df_30d["High"].iloc[:, 0] if isinstance(df_30d["High"], pd.DataFrame) else df_30d["High"])
                                low_30d = (df_30d["Low"].iloc[:, 0] if isinstance(df_30d["Low"], pd.DataFrame) else df_30d["Low"])

                                end_price_30d = float(close_30d.iloc[-1])
                                max_post_price = float(high_30d.max())
                                min_post_price = float(low_30d.min())

                                update_data.update({
                                    "end_preis_30d": round(end_price_30d, 2),
                                    "max_preis_30d": round(max_post_price, 2),
                                    "min_preis_30d": round(min_post_price, 2),
                                    "max_performance_30d": round(((max_post_price - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                    "min_performance_30d": round(((min_post_price - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                    "performance_30d_end_pct": round(((end_price_30d - base_preis) / base_preis) * 100, 2) if base_preis > 0 else 0,
                                    "status": "Ausgewertet (30D komplett)",
                                })
                    except Exception as e:
                        print(f"Fehler bei Joris-ID {sig_id} ({ticker}): {e}")

                if update_data:
                    self.supabase.table(self.table_joris_journal).update(update_data).eq("id", sig_id).execute()
        except Exception as e:
            print(f"Fehler in joris_journal Auswertung: {e}")

    def process_post_exit_tracking(self):
        """Prüft geschlossene Trades im trade_journal, zieht einmalig Indikatoren aus meta_data 
        falls leer, und berechnet das 30-Tage-Post-Exit-Tracking.
        """
        try:
            today = datetime.now().date()
            
            res = (
                self.supabase.table(self.table_trade_journal)
                .select("*")
                .eq("status", "Geschlossen")
                .eq("aris_status_30d", False) 
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
                exit_date_str = trade.get("ausstieg_datum_zeit")
                exit_price = float(trade.get("ausstiegskurs", 0))

                if not trade_id or not ticker or not exit_date_str:
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

                if days_passed >= 30:
                    try:
                        end_date = exit_date + timedelta(days=45) 
                        df_post = yf.download(
                            ticker,
                            start=exit_date.strftime("%Y-%m-%d"),
                            end=end_date.strftime("%Y-%m-%d"),
                            progress=False,
                            auto_adjust=True,
                        )

                        if not df_post.empty and "Close" in df_post:
                            df_30d = df_post.head(30)
                            if not df_30d.empty:
                                close_series = (
                                    df_post["Close"].iloc[:, 0]
                                    if isinstance(df_post["Close"], pd.DataFrame)
                                    else df_post["Close"]
                                )
                                high_series = (
                                    df_post["High"].iloc[:, 0]
                                    if isinstance(df_post["High"], pd.DataFrame)
                                    else df_post["High"]
                                )
                                min_series = (
                                    df_post["Low"].iloc[:, 0]
                                    if isinstance(df_post["Low"], pd.DataFrame)
                                    else df_post["Low"]
                                )

                                end_price_30d = float(close_series.iloc[-1])
                                max_post_price = float(high_series.max())
                                min_post_price = float(min_series.min())

                                perf_after_end = (
                                    ((end_price_30d - exit_price) / exit_price) * 100
                                    if exit_price > 0
                                    else 0
                                )
                                perf_after_max = (
                                    ((max_post_price - exit_price) / exit_price) * 100
                                    if exit_price > 0
                                    else 0
                                )
                                drawdown_after = (
                                    ((min_post_price - exit_price) / exit_price) * 100
                                    if exit_price > 0
                                    else 0
                                )

                                update_data.update({
                                    "end_preis_30d": round(end_price_30d, 2),
                                    "max_preis_30d": round(max_post_price, 2),
                                    "min_preis_30d": round(min_post_price, 2),
                                    "verpasste_aufwärtsbewegung_pct": round(perf_after_max, 2),
                                    "maximaler_drawdown_danach_pct": round(drawdown_after, 2),
                                    "performance_30d_end_pct": round(perf_after_end, 2)
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

    print("Nino startet Post-Exit-Tracking (30-Tage Tracking für Trade Journal)...")
    nino.process_post_exit_tracking()

    print("Nino Routinen erfolgreich beendet.")