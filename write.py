from db import get_db_client
import datetime

supabase = get_db_client()

# Was ist der Cutoff?
cutoff = (datetime.datetime.now() - datetime.timedelta(hours=24)).isoformat()
print(f"Aktueller Cutoff-Zeitpunkt: {cutoff}")

# Was liegt in der DB?
response = supabase.table("signals").select("ticker, created_at").limit(5).execute()
print(f"Daten in der DB: {response.data}")