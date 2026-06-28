import sqlite3
db = sqlite3.connect('/opt/jockey/backend/jockey_driver.db')
tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    print(t[0])
db.close()
