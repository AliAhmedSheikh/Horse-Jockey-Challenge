import sqlite3
db = sqlite3.connect('/opt/jockey/backend/jockey_driver.db')
c = db.cursor()
rows = c.execute("SELECT p.name, pr.bookmaker_name, pr.price FROM prices pr JOIN participants p ON pr.participant_id = p.id WHERE pr.bookmaker_name='AI' LIMIT 10").fetchall()
if rows:
    for r in rows:
        print(r)
else:
    print("No rows found - 'AI' bookmaker_name does not exist in prices table")
print("\nAll distinct bookmaker_names in prices table:")
for r in c.execute("SELECT DISTINCT bookmaker_name FROM prices").fetchall():
    print(f"  {r[0]}")
db.close()
