from datetime import datetime
from time_utils import AU_TZ

now = datetime.now(AU_TZ)
print(f"Now AEST: {now}")

import sqlite3
conn = sqlite3.connect("/opt/jockey/backend/jockey_driver.db")
c = conn.cursor()
c.execute("SELECT id, name, type, status, scheduled_time, completed_races, total_races, created_at, updated_at FROM meetings ORDER BY type, scheduled_time")
for r in c.fetchall():
    st = r[4]
    print(f"  {r[0]:6s} | {r[2]:7s} | {r[3]:10s} | sched={st} | {r[5]}/{r[6]:2d} | created={r[7]} | updated={r[8]} | {r[1]}")
conn.close()
