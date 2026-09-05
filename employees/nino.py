import os
import sys
import json
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# Hauptverzeichnis in den Pfad aufnehmen, um `db.py` korrekt zu finden
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from db import get_db_client

class NinoSignalsAssistant:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Nino (Signals Assistent)"
        self.description = "Scannt täglich neue Screener-Signale, archiviert sie (inkl. SMI, ADX, Favoriten & EMA20-Status) und wertet nach 5 Tagen aus."
        self.table_journal = "signal_journal"
        self.table_active_signals = "signals"
        self.table_favorites = "favorites"

    def daily_routine(self):
        logs = []
        
        # --- SCHRITT 1: Favoriten laden ---
        favorite_tickers = set()
        try:
            fav_res = self.supabase.table(self.table_favorites).select("ticker").execute()
            if fav_res.data:
                favorite_tickers = {row['ticker'].upper() for row in fav_res.data if row.get('ticker')}
        except Exception as e:
            logs.append(f"Hinweis beim Laden der Favoriten: {e}")

        # --- SCHRITT 2: Neue Signale ins Journal holen & EMA20 prüfen ---
        try:
            active_res = self.supabase.table(self.table_active_signals).select("*").execute()
            active_signals = active_res.data or []
            
            journal_res = self.supabase.table(self.table_journal).select("ticker, signal_datum").execute()
            journal_data = journal_res.data or []
            existing_set = {(j['ticker'], str(j['signal_datum'])[:10]) for j in journal_data if j.get('signal_datum')}

            for sig in active_signals:
                ticker = sig.get('ticker')
                if not ticker:
                    continue
                
                ticker_upper = ticker.upper()
                sig_date_str = sig.get('datum') or sig.get('signal_datum') or sig.get('candle_time')
                sig_type = sig.get('signal_type') or sig.get('signal_typ', 'Standard')
                sig_price = float(sig.get('entry_price') or sig.get('preis', 0))

                if not sig_date_str:
                    continue

                sig_date_iso = pd.to_datetime(sig_date_str).strftime('%Y-%m-%d')

                if (ticker_upper, sig_date_iso) not in existing_set:
                    # Meta-Daten (SMI & ADX) parsen
                    meta_raw = sig.get('meta_data', '{}')
                    smi_val, adx_val = None, None
                    
                    try:
                        if isinstance(meta_raw, str):
                            meta_dict = json.loads(meta_raw.replace("'", '"'))
                        elif isinstance(meta_raw, dict):
                            meta_dict = meta_raw
                        else:
                            meta_dict = {}
                            
                        smi_val = meta_dict.get('smi')
                        adx_val = meta_dict.get('adx')
                    except Exception:
                        pass

                    # Favoriten-Status prüfen
                    is_fav = ticker_upper in favorite_tickers

                    # EMA 20 Status ermitteln (ob Kurs über oder unter EMA 20 liegt)
                    above_ema = False
                    try:
                        df_ema = yf.download(ticker_upper, period="2mo", interval="1d", progress=False, auto_adjust=True)
                        if isinstance(df_ema.columns, pd.MultiIndex):
                            df_ema.columns = df_ema.columns.get_level_values(0)
                        if 'Close' in df_ema.columns and len(df_ema) >= 20:
                            ema_series = df_ema['Close'].ewm(span=20, adjust=False).mean()
                            # Letzter bekannter Wert vor oder am Signal-Datum
                            target_dt = pd.to_datetime(sig_date_iso)
                            historical_slice = df_ema[df_ema.index <= target_dt]
                            if not historical_slice.empty:
                                last_close = float(historical_slice['Close'].iloc[-1])
                                last_ema = float(ema_series.loc[historical_slice.index[-1]])
                                above_ema = last_close >= last_ema
                    except Exception:
                        pass

                    # Ins Journal schreiben
                    self.supabase.table(self.table_journal).insert({
                        "ticker": ticker_upper,
                        "signal_datum": pd.to_datetime(sig_date_str).isoformat(),
                        "signal_typ": sig_type,
                        "einstiegspreis_zum_signal": sig_price,
                        "smi": float(smi_val) if smi_val is not None else None,
                        "adx": float(adx_val) if adx_val is not None else None,
                        "is_favorite": is_fav,
                        "above_ema20": above_ema,
                        "status": "Offen (warte auf 5D)"
                    }).execute()
                    
                    logs.append(f"Neu im Journal: {ticker_upper} | Fav: {is_fav} | Über EMA20: {above_ema}")

        except Exception as e:
            logs.append(f"Fehler beim Einlesen neuer Signale: {e}")

        # --- SCHRITT 3: 5-Tages-Auswertung für offene Signale ---
        try:
            pending_res = self.supabase.table(self.table_journal).select("*").eq("status", "Offen (warte auf 5D)").execute()
            pending_signals = pending_res.data or []
            today = datetime.now().date()

            for sig in pending_signals:
                sig_id = sig.get('id')
                ticker = sig.get('ticker')
                sig_datum_raw = sig.get('signal_datum')
                
                if not sig_id or not ticker or not sig_datum_raw:
                    continue

                sig_date = pd.to_datetime(sig_datum_raw).date()
                days_passed = (today - sig_date).days
                
                if days_passed >= 5:
                    end_date = today + timedelta(days=2)
                    df_hist = yf.download(
                        ticker, 
                        start=sig_date.strftime('%Y-%m-%d'), 
                        end=end_date.strftime('%Y-%m-%d'), 
                        progress=False, 
                        auto_adjust=True
                    )

                    if not df_hist.empty and len(df_hist) >= 5:
                        df_5d = df_hist.head(5)

                        if isinstance(df_5d['High'], pd.DataFrame):
                            high_series = df_5d['High'].iloc[:, 0]
                            close_series = df_5d['Close'].iloc[:, 0]
                        else:
                            high_series = df_5d['High']
                            close_series = df_5d['Close']

                        max_kurs = float(high_series.max())
                        end_kurs = float(close_series.iloc[-1])
                        base_preis = float(sig.get('einstiegspreis_zum_signal', 0))

                        if base_preis == 0:
                            base_preis = float(close_series.iloc[0])

                        max_perf_pct = ((max_kurs - base_preis) / base_preis) * 100 if base_preis > 0 else 0
                        end_perf_pct = ((end_kurs - base_preis) / base_preis) * 100 if base_preis > 0 else 0

                        self.supabase.table(self.table_journal).update({
                            "max_kurs_5_tage": max_kurs,
                            "max_performance_5_tage": max_perf_pct,
                            "end_kurs_5_tage": end_kurs,
                            "end_performance_5_tage": end_perf_pct,
                            "status": "Ausgewertet (5D)"
                        }).eq("id", sig_id).execute()

                        logs.append(f"Ausgewertet (5D): {ticker} | Peak: {max_perf_pct:+.2f}%")

        except Exception as e:
            logs.append(f"Fehler bei der 5-Tages-Auswertung: {e}")

        return logs

    def get_signals_history(self):
        try:
            res = self.supabase.table(self.table_journal).select("*").order("signal_datum", desc=True).execute()
            return res.data if res.data else []
        except Exception:
            return []

if __name__ == "__main__":
    print("Nino startet seine Schicht...")
    supabase_client = get_db_client()
    nino = NinoSignalsAssistant(supabase_client)
    
    routine_logs = nino.daily_routine()
    for log in routine_logs:
        print(f"[Nino Log]: {log}")
        
    print("Nino hat seine Schicht beendet.")