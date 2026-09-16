from datetime import datetime
import pandas as pd
from db import get_db_client


class LeopoldAssistant:

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.table_joris_journal = "joris_journal"
        self.table_aris_arbeitsspeicher = "aris_arbeitsspeicher"

    def run_transfer_routine(self):
        """
        Leopolds eigenständige Routine:
        1. Prüft, ob bei joris_journal in der Spalte max_performance_5_tage eine Zahl vorliegt.
        2. Filtert Einträge heraus, bei denen aris_übertrag noch nicht True ist.
        3. Überträgt die Daten in aris_arbeitsspeicher.
        4. Setzt aris_übertrag bei joris_journal auf True.
        """
        print("Leopold startet seine Arbeitsroutine...")
        
        try:
            # Relevante Einträge aus joris_journal laden
            res = (
                self.supabase.table(self.table_joris_journal)
                .select("*")
                .not_.is_("max_performance_5_tage", "null")
                .neq("aris_übertrag", True)
                .execute()
            )
            
            entries = res.data or []
            if not entries:
                print("Leopold: Keine neuen Einträge im Joris Journal zur Übertragung gefunden.")
                return

            success_count = 0
            for entry in entries:
                entry_id = entry.get("id")
                ticker = entry.get("ticker")

                if not entry_id or not ticker:
                    continue

                # Payload für aris_arbeitsspeicher zusammenstellen
                payload = {
                    "created_at": datetime.utcnow().isoformat(),
                    "quelle": "joris_journal",
                    "ticker": ticker,
                    "unternehmen": entry.get("unternehmen"),
                    "signal_typ": entry.get("signal_typ") or entry.get("signal_typ"),
                    "max_performance_5_tage": entry.get("max_performance_5_tage"),
                    "end_performance_5_tage": entry.get("end_performance_5_tage")
                }

                try:
                    # In aris_arbeitsspeicher schreiben
                    self.supabase.table(self.table_aris_arbeitsspeicher).insert(payload).execute()

                    # In joris_journal das Flag aris_übertrag auf True setzen
                    self.supabase.table(self.table_joris_journal).update({"aris_übertrag": True}).eq("id", entry_id).execute()
                    
                    success_count += 1
                    print(f"Leopold: Ticker {ticker} erfolgreich verarbeitet und übertragen.")
                
                except Exception as inner_err:
                    print(f"Leopold: Fehler beim Übertragen von Ticker {ticker}: {inner_err}")

            print(f"Leopold: Routine beendet. {success_count} Datensätze erfolgreich übertragen.")

        except Exception as e:
            print(f"Leopold: Schwerwiegender Fehler in der Routine: {e}")

    def get_aris_arbeitsspeicher_data(self):
        """Liefert die Daten für die Benutzeroberfläche (Leopold-Tab auf der Team-Seite)."""
        try:
            res = (
                self.supabase.table(self.table_aris_arbeitsspeicher)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            return res.data if res.data else []
        except Exception as e:
            print(f"Leopold: Fehler beim Laden des Aris-Arbeitsspeichers: {e}")
            return []


if __name__ == "__main__":
    # Eigenständiger Startpunkt für Leopolds Prozess (z.B. per Cronjob oder manuellem Skriptaufruf)
    supabase_client = get_db_client()
    leopold = LeopoldAssistant(supabase_client)
    
    leopold.run_transfer_routine()