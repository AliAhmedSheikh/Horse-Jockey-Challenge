"""Backfill missing zero-point results for all participants.

Every participant rode in every race. If Ladbrokes API didn't return their
position, we create a pos=99 result with 0 points so completed_races is accurate.
"""
import sqlite3

c = sqlite3.connect('/opt/jockey/backend/jockey_driver.db')
c.execute('PRAGMA journal_mode=WAL')
cur = c.cursor()

meetings = cur.execute('SELECT id, name, total_races FROM meetings').fetchall()

total_backfilled = 0
for mid, mname, total_races in meetings:
    participants = cur.execute('SELECT id, name FROM participants WHERE meeting_id=?', (mid,)).fetchall()

    for pid, pname in participants:
        has_result = set(r[0] for r in cur.execute(
            'SELECT DISTINCT race_number FROM results WHERE meeting_id=? AND participant_id=?',
            (mid, pid)
        ).fetchall())

        all_races = set(range(1, total_races + 1))
        missing = all_races - has_result

        for race_num in missing:
            cur.execute(
                'INSERT OR IGNORE INTO results (meeting_id, participant_id, race_number, position, points_added, final_points) VALUES (?, ?, ?, 99, 0, 0)',
                (mid, pid, race_num)
            )
            total_backfilled += 1

    # Recalculate current_points, completed_races, remaining_races
    for pid, pname in participants:
        results = cur.execute(
            'SELECT SUM(points_added), COUNT(DISTINCT race_number) FROM results WHERE meeting_id=? AND participant_id=?',
            (mid, pid)
        ).fetchone()
        total_pts = results[0] or 0
        completed = results[1] or 0
        remaining = total_races - completed
        cur.execute(
            'UPDATE participants SET current_points=?, completed_races=?, remaining_races=? WHERE id=?',
            (total_pts, completed, remaining, pid)
        )

c.commit()
print(f'Backfilled {total_backfilled} missing result records')

# Verify
print('\n=== VERIFICATION ===')
for mid, mname, total_races in meetings:
    pcount = cur.execute('SELECT COUNT(*) FROM participants WHERE meeting_id=?', (mid,)).fetchone()[0]
    rcount = cur.execute('SELECT COUNT(*) FROM results WHERE meeting_id=?', (mid,)).fetchone()[0]
    avg = rcount / pcount if pcount > 0 else 0
    print(f'{mname}: {pcount} participants, {rcount} results, avg {avg:.1f} per participant (should be {total_races})')

# Top 3 by points
print('\n=== TOP 3 BY POINTS (REDCLIFFE) ===')
mid = cur.execute("SELECT id FROM meetings WHERE name='REDCLIFFE'").fetchone()[0]
top3 = cur.execute("""
    SELECT name, current_points, completed_races 
    FROM participants 
    WHERE meeting_id=? 
    ORDER BY current_points DESC 
    LIMIT 3
""", (mid,)).fetchall()
for name, pts, comp in top3:
    print(f'  {name}: {pts}pts in {comp} races')

print('\n=== TOP 3 BY POINTS (MELTON) ===')
mid = cur.execute("SELECT id FROM meetings WHERE name='MELTON'").fetchone()[0]
top3 = cur.execute("""
    SELECT name, current_points, completed_races 
    FROM participants 
    WHERE meeting_id=? 
    ORDER BY current_points DESC 
    LIMIT 3
""", (mid,)).fetchall()
for name, pts, comp in top3:
    print(f'  {name}: {pts}pts in {comp} races')

print('\n=== TOP 3 BY POINTS (Randwick) ===')
mid = cur.execute("SELECT id FROM meetings WHERE name='Randwick'").fetchone()[0]
top3 = cur.execute("""
    SELECT name, current_points, completed_races 
    FROM participants 
    WHERE meeting_id=? 
    ORDER BY current_points DESC 
    LIMIT 3
""", (mid,)).fetchall()
for name, pts, comp in top3:
    print(f'  {name}: {pts}pts in {comp} races')

c.close()
