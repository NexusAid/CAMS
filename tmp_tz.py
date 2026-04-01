from datetime import datetime
import time
import os

os.environ['TZ'] = 'Africa/Nairobi'
time.tzset()

val = "2026-03-23T10:30"
local_dt = datetime.strptime(val, "%Y-%m-%dT%H:%M")
print("Local DT parsed:", local_dt)

# Convert to aware local datetime
aware_dt = local_dt.astimezone()
print("Aware DT:", aware_dt)

utc_dt = aware_dt.astimezone(datetime.utcnow().astimezone().tzinfo) # not quite
