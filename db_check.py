import sqlite3
db = sqlite3.connect('/opt/jockey/backend/jockey_driver.db')
c = db.cursor()
print("=== Price count ===")
print(c.execute("SELECT COUNT(*) FROM prices").fetchone()[0])
print("\n=== Bookmaker names ===")
for r in c.execute("SELECT DISTINCT bookmaker_name FROM prices").fetchall():
    print(r[0])
print("\n=== Sample prices ===")
for r in c.execute("SELECT participant_id, bookmaker_name, price FROM prices LIMIT 10").fetchall():
    print(r)
db.close()
