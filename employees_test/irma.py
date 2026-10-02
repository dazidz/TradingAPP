# employees_test/irma.py
import pandas as pd


class IrmaSectorAssistant:
    """Irma – Sektor-Assistenz

    Zuständig für Sektor-Rotation und Berechnung der Signal-Quoten 
    (Anzahl Signale / Gesamt-Ticker im Sektor).
    """

    def __init__(self, supabase_client):
        self.name = "Irma"
        self.role = "Sektor-Assistenz"
        self.supabase = supabase_client

    def get_top_sector_quotas(self) -> pd.DataFrame:
        """Ermittelt die Top 5 Sektoren nach prozentualem Signal-Anteil."""
        if not self.supabase:
            return pd.DataFrame()

        # 1. Watchlist laden (Gesamt-Ticker pro Sektor)
        wl_res = self.supabase.table("watchlist").select("ticker, sector").execute()
        wl_data = wl_res.data if wl_res.data else []
        if not wl_data:
            return pd.DataFrame()

        sector_stats = {}
        for item in wl_data:
            sec = item.get("sector") or "Unbekannt"
            tick = item.get("ticker")
            if not tick:
                continue
            if sec not in sector_stats:
                sector_stats[sec] = set()
            sector_stats[sec].add(tick)

        # 2. Aktive Signale laden
        sig_res = self.supabase.table("signals").select("ticker").execute()
        sig_data = sig_res.data if sig_res.data else []
        active_signals = {item.get("ticker") for item in sig_data if item.get("ticker")}

        # 3. Quoten berechnen
        rows = []
        for sec, tickers in sector_stats.items():
            total = len(tickers)
            if total == 0:
                continue
            signaled = len(tickers.intersection(active_signals))
            quota = (signaled / total) * 100
            rows.append({
                "sector": sec,
                "total_tickers": total,
                "signal_tickers": signaled,
                "signal_quota_percent": round(quota, 2)
            })

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        # Absteigend nach Quote sortieren und Top 5 nehmen
        df = df.sort_values(by="signal_quota_percent", ascending=False).head(5)
        return df