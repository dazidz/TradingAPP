import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

class NinoSignalsAssistant:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Nino (Signals Assistent)"
        self.description = "Scannt täglich neue Screener-Signale, archiviert sie und wertet nach 5 Tagen den Peak und Schlusskurs aus."
        self.table_journal = "nino_log"
        self.table_active_signals = "signals"

    def daily_routine(self):
        logs = []
        
        # --- SCHRITT 1: Neue Signale ins Journal holen ---
        try:
            active_res = self.supabase.table(self.table_active_signals).select("*").execute()
            active_signals = active_res.data or []
            
            journal_res = self.supabase.table(self.table_journal).select("ticker, signal_datum").execute()
            journal_data = journal_res.data or []
            existing_set = {(j['ticker'], str(j['signal_datum'])[:10]) for j in journal_data if j.get('signal_datum')}

            for sig in active_signals:
                ticker = sig.get('ticker')
                sig_date_str = sig.get('datum') or sig.get('signal_datum')
                sig_type = sig.get('signal_typ', 'Standard')
                sig_price = float(sig.get('preis', 0))

                if not ticker or not sig_date_str:
                    continue

                sig_date_iso = pd.to_datetime(sig_date_str).strftime('%Y-%m-%d')

                if (ticker.upper(), sig_date_iso) not in existing_set:
                    self.supabase.table(self.table_journal).insert({
                        "ticker": ticker.upper(),
                        "signal_datum": pd.to_datetime(sig_date_str).isoformat(),
                        "signal_typ": sig_type,
                        "einstiegspreis_zum_signal": sig_price,
                        "status": "Offen (warte auf 5D)"
                    }).execute()
                    logs.append(f"Neu im Journal: {ticker} vom {sig_date_iso}")

        except Exception as e:
            print("------------ SUPABASE FEHLER DETAILS ------------")
            print(f"Typ: {type(e)}")
            print(f"Fehler: {e}")
            if hasattr(e, 'code'):
                print(f"Code: {e.code}")
            if hasattr(e, 'message'):
                print(f"Message: {e.message}")
            print("---------------------------------------------------")
            logs.append(f"Fehler beim Einlesen neuer Signale: {e}")

        # --- SCHRITT 2: Auswertung für Signale nach 5 Handelstagen ---
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


# --- Direkter Ausführungspunkt für GitHub Actions ---
if __name__ == "__main__":
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        print("Fehler: SUPABASE_URL oder SUPABASE_KEY sind nicht gesetzt!")
        sys.exit(1)

    print("Nino startet seine automatisierte Schicht...")
    supabase_client = create_client(url, key)
    nino = NinoSignalsAssistant(supabase_client)
    
    routine_logs = nino.daily_routine()
    for log in routine_logs:
        print(f"[Nino Log]: {log}")
        
    print("Nino hat seine Schicht beendet.")