import os
from supabase import create_client
from employees.nino import NinoSignalsAssistant

# Liest die Secrets aus den Umgebungsvariablen (die gleich von GitHub bereitgestellt werden)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    print("Fehler: Supabase Credentials fehlen in den Environment Variables.")
    exit(1)

supabase = create_client(URL, KEY)
nino = NinoSignalsAssistant(supabase)

print("Nino startet seine automatisierte Schicht...")
logs = nino.daily_routine()

if logs:
    for log in logs:
        print(f"[Nino Log]: {log}")
else:
    print("Nino hat gearbeitet: Keine neuen Aktionen oder Updates.")