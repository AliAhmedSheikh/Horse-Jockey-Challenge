import sqlite3
db = sqlite3.connect('/opt/jockey/backend/jockey_driver.db')
c = db.cursor()

print("=== Bookmaker counts ===")
for r in c.execute("SELECT bookmaker_name, COUNT(*) as count FROM prices GROUP BY bookmaker_name"):
    print(f"  {r[0]}: {r[1]}")

print("\n=== TABtouch_PreRace records ===")
for r in c.execute("SELECT participant_id, bookmaker_name, price FROM prices WHERE bookmaker_name='TABtouch_PreRace' LIMIT 10"):
    print(f"  {r[0]} | {r[1]} | {r[2]}")

print(f"\n=== Total: {c.execute('SELECT COUNT(*) FROM prices').fetchone()[0]} ===")
db.close()
