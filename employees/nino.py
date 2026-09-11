from datetime import datetime, timedelta
import json
import os
import pandas as pd
import yfinance as yf


class NinoSignalsAssistant:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.table_journal = "signals_journal"  # Hier das 's' ergänzt!
    self.table_active_signals = "signals"
    self.table_favorites = "favorites"
    self.table_joris_journal = "joris_journal"

  def background_routine(self):
    """Ninos autonome Aufgabe: Prüft Signale, gleicht das Journal ab und berechnet die 5-Tages-Performance."""
    favorite_tickers = set()
    try:
      fav_res = (
          self.supabase.table(self.table_favorites).select("ticker").execute()
      )
      if fav_res.data:
        favorite_tickers = {
            row["ticker"].upper() for row in fav_res.data if row.get("ticker")
        }
    except Exception:
      pass

    try:
      active_res = (
          self.supabase.table(self.table_active_signals).select("*").execute()
      )
      active_signals = active_res.data or []

      journal_res = (
          self.supabase.table(self.table_journal)
          .select("ticker, signal_datum")
          .execute()
      )
      journal_data = journal_res.data or []
      existing_set = {
          (j["ticker"], str(j["signal_datum"])[:10])
          for j in journal_data
          if j.get("signal_datum")
      }

      for sig in active_signals:
        ticker = sig.get("ticker")
        if not ticker:
          continue

        ticker_upper = ticker.upper()
        sig_date_str = (
            sig.get("datum")
            or sig.get("signal_datum")
            or sig.get("candle_time")
        )
        sig_type = sig.get("signal_type") or sig.get("signal_typ", "Standard")
        sig_price = float(sig.get("entry_price") or sig.get("preis", 0))

        if not sig_date_str:
          continue
        sig_date_iso = pd.to_datetime(sig_date_str).strftime("%Y-%m-%d")

        if (ticker_upper, sig_date_iso) not in existing_set:
          meta_raw = sig.get("meta_data", "{}")
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

          is_fav = ticker_upper in favorite_tickers

          self.supabase.table(self.table_journal).insert({
              "ticker": ticker_upper,
              "signal_datum": pd.to_datetime(sig_date_str).isoformat(),
              "signal_typ": sig_type,
              "einstiegspreis_zum_signal": sig_price,
              "smi": float(smi_val) if smi_val is not None else None,
              "adx": float(adx_val) if adx_val is not None else None,
              "is_favorite": is_fav,
              "above_ema20": above_ema,
              "status": "Offen (warte auf 5D)",
          }).execute()
    except Exception:
      pass

    # 1. Signale auswerten (5 Tage & 4 Wochen)
    try:
      pending_res = (
          self.supabase.table(self.table_journal)
          .select("*")
          .in_(
              "status",
              ["Offen (warte auf 5D)", "Ausgewertet (5D)", "active"],
          )
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

        if days_passed >= 5:
          try:
            df_hist = yf.download(
                ticker,
                start=sig_date.strftime("%Y-%m-%d"),
                end=(today + timedelta(days=2)).strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )

            if not df_hist.empty and len(df_hist) >= 5:
              df_5d = df_hist.head(5)
              high_series = (
                  df_5d["High"].iloc[:, 0]
                  if isinstance(df_5d["High"], pd.DataFrame)
                  else df_5d["High"]
              )
              close_series = (
                  df_5d["Close"].iloc[:, 0]
                  if isinstance(df_5d["Close"], pd.DataFrame)
                  else df_5d["Close"]
              )

              max_kurs = float(high_series.max())
              end_kurs = float(close_series.iloc[-1])
              base_preis = float(sig.get("einstiegspreis_zum_signal", 0)) or float(
                  close_series.iloc[0]
              )

              max_perf_pct = (
                  ((max_kurs - base_preis) / base_preis) * 100
                  if base_preis > 0
                  else 0
              )
              end_perf_pct = (
                  ((end_kurs - base_preis) / base_preis) * 100
                  if base_preis > 0
                  else 0
              )

              update_data = {
                  "max_kurs_5_tage": max_kurs,
                  "max_performance_5_tage": max_perf_pct,
                  "end_kurs_5_tage": end_kurs,
                  "end_performance_5_tage": end_perf_pct,
                  "status": "Ausgewertet (5D)",
              }

              # 4-Wochen-Check (ca. 28 Tage)
              if days_passed >= 28 and len(df_hist) >= 20:
                end_kurs_4w = float(
                    (
                        df_hist["Close"].iloc[:, 0]
                        if isinstance(df_hist["Close"], pd.DataFrame)
                        else df_hist["Close"]
                    ).iloc[-1]
                )
                end_perf_4w = (
                    ((end_kurs_4w - base_preis) / base_preis) * 100
                    if base_preis > 0
                    else 0
                )
                update_data["performance_1_monat"] = end_perf_4w
                update_data["status"] = "Ausgewertet (5T & 4W)"

              self.supabase.table(self.table_journal).update(update_data).eq(
                  "id", sig_id
              ).execute()
          except Exception:
            pass
    except Exception:
      pass

    # 2. Joris Journal (Swing-Picks) auswerten (5 Tage & 4 Wochen)
    try:
      joris_pending = (
          self.supabase.table(self.table_joris_journal)
          .select("*")
          .in_("status", ["active", "Ausgewertet (5D)"])
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

        sig_date = pd.to_datetime(sig_datum_raw).date()
        days_passed = (today - sig_date).days

        if days_passed >= 5:
          try:
            df_hist = yf.download(
                ticker,
                start=sig_date.strftime("%Y-%m-%d"),
                end=(today + timedelta(days=2)).strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )

            if not df_hist.empty and len(df_hist) >= 5:
              df_5d = df_hist.head(5)
              high_series = (
                  df_5d["High"].iloc[:, 0]
                  if isinstance(df_5d["High"], pd.DataFrame)
                  else df_5d["High"]
              )
              close_series = (
                  df_5d["Close"].iloc[:, 0]
                  if isinstance(df_5d["Close"], pd.DataFrame)
                  else df_5d["Close"]
              )

              max_kurs = float(high_series.max())
              end_kurs = float(close_series.iloc[-1])
              # Falls kein Einstiegspreis hinterlegt ist, nehmen wir den Startkurs des ersten Tages
              base_preis = float(close_series.iloc[0])

              max_perf_pct = (
                  ((max_kurs - base_preis) / base_preis) * 100
                  if base_preis > 0
                  else 0
              )
              end_perf_pct = (
                  ((end_kurs - base_preis) / base_preis) * 100
                  if base_preis > 0
                  else 0
              )

              update_data = {
                  "max_kurs_5_tage": max_kurs,
                  "max_performance_5_tage": max_perf_pct,
                  "end_kurs_5_tage": end_kurs,
                  "end_performance_5_tage": end_perf_pct,
                  "status": "Ausgewertet (5D)",
              }

              if days_passed >= 28 and len(df_hist) >= 20:
                end_kurs_4w = float(
                    (
                        df_hist["Close"].iloc[:, 0]
                        if isinstance(df_hist["Close"], pd.DataFrame)
                        else df_hist["Close"]
                    ).iloc[-1]
                )
                end_perf_4w = (
                    ((end_kurs_4w - base_preis) / base_preis) * 100
                    if base_preis > 0
                    else 0
                )
                update_data["performance_1_monat"] = end_perf_4w
                update_data["status"] = "Ausgewertet (5T & 4W)"

              self.supabase.table(self.table_joris_journal).update(
                  update_data
              ).eq("id", sig_id).execute()
          except Exception:
            pass
    except Exception:
      pass

  def get_signals_history(self):
    """Holt das fertige Journal aus der Datenbank für die Dashboard-Ansicht"""
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
    """Holt das Joris-Journal aus der Datenbank"""
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