import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

class NinoSignalsAssistant:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Nino (Signals Assistent)"
        self.description = "Scannt täglich neue Screener-Signale, archiviert sie und wertet nach 5 Tagen den Peak und Schlusskurs aus."
        self.table_journal = "signals_journal"
        self.table_active_signals = "signals"  # Deine aktive Screener-Tabelle

    def daily_routine(self):
        """
        Nino führt seine tägliche Schicht aus:
        1. Neue Signale aus der aktiven Tabelle ins Journal holen.
        2. Offene Signale, die 5 Tage alt sind, final auswerten und updaten.
        """
        logs = []
        
        # --- SCHRITT 1: Neue Signale ins Journal holen ---
        try:
            active_res = self.supabase.table(self.table_active_signals).select("*").execute()
            active_signals = active_res.data
            
            # Bereits im Journal vorhandene Ticker/Datums-Kombinationen prüfen, um Duplikate zu vermeiden
            journal_res = self.supabase.table(self.table_journal).select("ticker, signal_datum").execute()
            existing_set = {(j['ticker'], j['signal_datum'][:10]) for j in journal_res.data}

            for sig in active_signals:
                ticker = sig.get('ticker')
                sig_date_str = sig.get('datum') or sig.get('signal_datum') # Passe das Feld an deine DB an
                sig_type = sig.get('signal_typ', 'Standard')
                sig_price = float(sig.get('preis', 0))

                if not sig_date_str:
                    continue

                sig_date_iso = pd.to_datetime(sig_date_str).strftime('%Y-%m-%d')

                # Wenn das Signal noch nicht im Journal ist, frisch aufnehmen
                if (ticker, sig_date_iso) not in existing_set:
                    self.supabase.table(self.table_journal).insert({
                        "ticker": ticker.upper(),
                        "signal_datum": pd.to_datetime(sig_date_str).isoformat(),
                        "signal_typ": sig_type,
                        "einstiegspreis_zum_signal": sig_price,
                        "status": "Offen (warte auf 5D)"
                    }).execute()
                    logs.append(f"Neu im Journal: {ticker} vom {sig_date_iso}")

        except Exception as e:
            logs.append(f"Fehler beim Einlesen neuer Signale: {e}")

        # --- SCHRITT 2: Auswertung für Signale nach 5 Handelstagen ---
        try:
            # Hole alle Signale, die noch den Status "Offen" haben
            pending_res = self.supabase.table(self.table_journal).select("*").eq("status", "Offen (warte auf 5D)").execute()
            pending_signals = pending_res.data

            today = datetime.now().date()

            for sig in pending_signals:
                sig_id = sig['id']
                ticker = sig['ticker']
                sig_date = pd.to_datetime(sig['signal_datum']).date()
                
                # Prüfen, ob ca. 5-7 Kalendertage vergangen sind (entspricht ~5 Handelstagen)
                days_passed = (today - sig_date).days
                
                if days_passed >= 5:
                    # Kursdaten ab Signal-Datum herunterladen
                    end_date = today + timedelta(days=2)
                    df_hist = yf.download(
                        ticker, 
                        start=sig_date.strftime('%Y-%m-%d'), 
                        end=end_date.strftime('%Y-%m-%d'), 
                        progress=False, 
                        auto_adjust=True
                    )

                    if len(df_hist) >= 5:
                        df_5d = df_hist.head(5)

                        # MultiIndex-Sicherheit für yfinance
                        if isinstance(df_5d['High'], pd.DataFrame):
                            high_series = df_5d['High'].iloc[:, 0]
                            close_series = df_5d['Close'].iloc[:, 0]
                        else:
                            high_series = df_5d['High']
                            close_series = df_5d['Close']

                        max_kurs = float(high_series.max())
                        end_kurs = float(close_series.iloc[-1])
                        base_preis = float(sig['einstiegspreis_zum_signal'])

                        if base_preis == 0:
                            base_preis = float(close_series.iloc[0])

                        # Performance berechnen
                        max_perf_pct = ((max_kurs - base_preis) / base_preis) * 100 if base_preis > 0 else 0
                        end_perf_pct = ((end_kurs - base_preis) / base_preis) * 100 if base_preis > 0 else 0

                        # Update in Supabase
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
        """Gibt das gesamte Journal für die UI zurück."""
        try:
            res = self.supabase.table(self.table_journal).select("*").order("signal_datum", desc=True).execute()
            return res.data
        except Exception:
            return []