import sqlite3
db = sqlite3.connect('/opt/jockey/backend/jockey_driver.db')
c = db.cursor()
for row in c.execute("SELECT id, name, status, total_races, completed_races FROM meetings ORDER BY id"):
    print(f"{row[0]:5s} {row[1]:30s} {row[2]:12s} {row[3]}/{row[4]}")
db.close()
