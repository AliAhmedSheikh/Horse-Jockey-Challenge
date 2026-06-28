import sqlite3
db = sqlite3.connect('/opt/jockey/backend/jockey_driver.db')
c = db.cursor()
mid = 'm7'
for table, col in [('bets', 'meeting_id'), ('results', 'meeting_id'), ('participants', 'meeting_id'), ('prices', 'meeting_id')]:
    count = c.execute(f'SELECT COUNT(*) FROM {table} WHERE {col} = ?', (mid,)).fetchone()[0]
    c.execute(f'DELETE FROM {table} WHERE {col} = ?', (mid,))
    print(f'  Deleted {count} from {table}')
c.execute('DELETE FROM meetings WHERE id = ?', (mid,))
print(f'{mid} (Gawler) deleted')
db.commit()
db.close()
print('Done')
