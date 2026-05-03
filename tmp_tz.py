from datetime import datetime, timezone, timedelta

# Africa/Nairobi is East Africa Time (EAT), which is permanently UTC+3.
nairobi_tz = timezone(timedelta(hours=3), name="Africa/Nairobi")

val = "2026-03-23T10:30"
# Parse naive local datetime
local_dt = datetime.strptime(val, "%Y-%m-%dT%H:%M")
print("Local DT parsed (naive):", local_dt)

# Convert to aware local datetime in Nairobi timezone
aware_dt = local_dt.replace(tzinfo=nairobi_tz)
print("Aware DT (Nairobi):", aware_dt)

# Convert to UTC
utc_dt = aware_dt.astimezone(timezone.utc)
print("UTC DT:", utc_dt)
