import sqlite3
conn = sqlite3.connect("/opt/jockey/backend/jockey_driver.db")
c = conn.cursor()

# Delete all today's data (wrong meetings)
c.execute("DELETE FROM results WHERE meeting_id IN (SELECT id FROM meetings WHERE date='2026-06-21')")
print(f"Deleted {c.rowcount} results")
c.execute("DELETE FROM prices WHERE meeting_id IN (SELECT id FROM meetings WHERE date='2026-06-21')")
print(f"Deleted {c.rowcount} prices")
c.execute("DELETE FROM participants WHERE meeting_id IN (SELECT id FROM meetings WHERE date='2026-06-21')")
print(f"Deleted {c.rowcount} participants")
c.execute("DELETE FROM meetings WHERE date='2026-06-21'")
print(f"Deleted {c.rowcount} meetings")

conn.commit()
conn.close()
print("Done - DB cleared for re-seed")
