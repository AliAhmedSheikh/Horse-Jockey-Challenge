import sqlite3
import json
import os

def main(ctx):
    db_path = r"C:\Users\mcn\Desktop\Jokey and driver challenge\jockey-driver-dashboard\backend\jockey_driver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    report = {}

    def fetchall_dict(query, params=()):
        c.execute(query, params)
        rows = c.fetchall()
        return [dict(row) for row in rows]

    # 1. Duplicate Result rows for same participant + race_number + meeting_id
    report["duplicate_results"] = fetchall_dict("""
        SELECT meeting_id, participant_id, race_number, COUNT(*) as cnt
        FROM results
        GROUP BY meeting_id, participant_id, race_number
        HAVING cnt > 1
    """)

    # 2. Participants with current_points != SUM of points_added from results
    report["points_mismatch"] = fetchall_dict("""
        SELECT p.id, p.meeting_id, p.name, p.current_points, SUM(r.points_added) as sum_points
        FROM participants p
        LEFT JOIN results r ON p.id = r.participant_id AND p.meeting_id = r.meeting_id
        GROUP BY p.id, p.meeting_id, p.name, p.current_points
        HAVING ABS(p.current_points - COALESCE(SUM(r.points_added), 0)) > 0.0001
    """)

    # 3. Meetings with status='finished' where completed_races != total_races
    report["finished_meeting_race_mismatch"] = fetchall_dict("""
        SELECT id, name, status, completed_races, total_races
        FROM meetings
        WHERE status = 'finished' AND completed_races != total_races
    """)

    # 4. Participants with completed_races > meeting.total_races
    report["participant_completed_over_total"] = fetchall_dict("""
        SELECT p.id, p.name, p.meeting_id, p.completed_races, m.total_races
        FROM participants p
        JOIN meetings m ON p.meeting_id = m.id
        WHERE p.completed_races > m.total_races
    """)

    # 5. Participants with remaining_races < 0
    report["negative_remaining_races"] = fetchall_dict("""
        SELECT p.id, p.name, p.meeting_id, p.remaining_races, m.total_races, p.completed_races
        FROM participants p
        JOIN meetings m ON p.meeting_id = m.id
        WHERE p.remaining_races < 0
    """)

    # 6. Orphaned results (meeting_id or participant_id missing)
    report["orphaned_results_meeting"] = fetchall_dict("""
        SELECT r.id, r.meeting_id, r.participant_id
        FROM results r
        LEFT JOIN meetings m ON r.meeting_id = m.id
        WHERE m.id IS NULL
    """)
    report["orphaned_results_participant"] = fetchall_dict("""
        SELECT r.id, r.meeting_id, r.participant_id
        FROM results r
        LEFT JOIN participants p ON r.participant_id = p.id
        WHERE p.id IS NULL
    """)

    # 7. Orphaned prices
    report["orphaned_prices_meeting"] = fetchall_dict("""
        SELECT pr.id, pr.meeting_id, pr.participant_id
        FROM prices pr
        LEFT JOIN meetings m ON pr.meeting_id = m.id
        WHERE m.id IS NULL
    """)
    report["orphaned_prices_participant"] = fetchall_dict("""
        SELECT pr.id, pr.meeting_id, pr.participant_id
        FROM prices pr
        LEFT JOIN participants p ON pr.participant_id = p.id
        WHERE p.id IS NULL
    """)

    # 8. Meetings with 0 participants
    report["meetings_with_zero_participants"] = fetchall_dict("""
        SELECT m.id, m.name, m.date, COUNT(p.id) as participant_count
        FROM meetings m
        LEFT JOIN participants p ON m.id = p.meeting_id
        GROUP BY m.id, m.name, m.date
        HAVING participant_count = 0
    """)

    # 9. Participants with 0 results despite meeting having completed_races > 0
    report["participants_zero_results_with_completed_meeting"] = fetchall_dict("""
        SELECT p.id, p.name, p.meeting_id, m.completed_races
        FROM participants p
        JOIN meetings m ON p.meeting_id = m.id
        WHERE m.completed_races > 0
          AND (SELECT COUNT(*) FROM results r WHERE r.participant_id = p.id AND r.meeting_id = p.meeting_id) = 0
    """)

    # 10. Duplicate participant names within same meeting_id
    report["duplicate_participant_names"] = fetchall_dict("""
        SELECT meeting_id, name, COUNT(*) as cnt
        FROM participants
        GROUP BY meeting_id, name
        HAVING cnt > 1
    """)

    # 11. Duplicate meeting names on same date
    report["duplicate_meeting_names"] = fetchall_dict("""
        SELECT date, name, COUNT(*) as cnt
        FROM meetings
        GROUP BY date, name
        HAVING cnt > 1
    """)

    # 12. For finished meetings, sum of all result rows vs expected total_races * number_of_participants
    report["finished_meeting_result_counts"] = fetchall_dict("""
        SELECT m.id, m.name, m.total_races, m.completed_races, COUNT(p.id) as num_participants,
               (SELECT COUNT(*) FROM results r WHERE r.meeting_id = m.id) as total_result_rows
        FROM meetings m
        LEFT JOIN participants p ON m.id = p.meeting_id
        WHERE m.status = 'finished'
        GROUP BY m.id, m.name, m.total_races, m.completed_races
    """)

    # 13. Points distribution per race (3,2,1,0)
    report["points_distribution_per_race"] = fetchall_dict("""
        SELECT meeting_id, race_number, points_added, COUNT(*) as cnt
        FROM results
        GROUP BY meeting_id, race_number, points_added
        ORDER BY meeting_id, race_number, points_added
    """)

    # 14. For any race, multiple participants with position=1
    report["multiple_position_1"] = fetchall_dict("""
        SELECT meeting_id, race_number, COUNT(*) as cnt
        FROM results
        WHERE position = 1
        GROUP BY meeting_id, race_number
        HAVING cnt > 1
    """)

    # 15. Negative current_points, negative points_added, weird positions (0 or null)
    report["negative_points"] = fetchall_dict("""
        SELECT id, meeting_id, name, current_points
        FROM participants
        WHERE current_points < 0
    """)
    report["negative_points_added"] = fetchall_dict("""
        SELECT id, participant_id, meeting_id, race_number, points_added, position
        FROM results
        WHERE points_added < 0
    """)
    report["weird_positions"] = fetchall_dict("""
        SELECT id, participant_id, meeting_id, race_number, position
        FROM results
        WHERE position = 0 OR position IS NULL
    """)

    # 16. Participant's completed_races count doesn't match number of Result rows they have for that meeting
    report["completed_races_vs_result_count"] = fetchall_dict("""
        SELECT p.id, p.name, p.meeting_id, p.completed_races, COUNT(r.id) as result_count
        FROM participants p
        LEFT JOIN results r ON p.id = r.participant_id AND p.meeting_id = r.meeting_id
        GROUP BY p.id, p.name, p.meeting_id, p.completed_races
        HAVING p.completed_races != COUNT(r.id)
    """)

    # Additional check: sum of points per race should be approx 6 (or 0 if no results?)
    report["race_points_sum"] = fetchall_dict("""
        SELECT meeting_id, race_number, COUNT(*) as num_results, SUM(points_added) as total_points
        FROM results
        GROUP BY meeting_id, race_number
    """)

    # Also check meeting total races vs result rows per participant
    report["result_rows_per_participant"] = fetchall_dict("""
        SELECT p.id, p.meeting_id, COUNT(r.id) as result_rows, m.total_races, m.completed_races
        FROM participants p
        JOIN meetings m ON p.meeting_id = m.id
        LEFT JOIN results r ON p.id = r.participant_id AND p.meeting_id = r.meeting_id
        GROUP BY p.id, p.meeting_id, m.total_races, m.completed_races
    """)

    # Check for participants with null or empty names
    report["empty_participant_names"] = fetchall_dict("""
        SELECT id, meeting_id, name
        FROM participants
        WHERE name IS NULL OR TRIM(name) = ''
    """)

    # Check for any meeting with null/empty name
    report["empty_meeting_names"] = fetchall_dict("""
        SELECT id, name, date
        FROM meetings
        WHERE name IS NULL OR TRIM(name) = ''
    """)

    # Check prices with null or 0 price
    report["zero_or_null_prices"] = fetchall_dict("""
        SELECT id, participant_id, meeting_id, bookmaker_name, price
        FROM prices
        WHERE price IS NULL OR price = 0
    """)

    conn.close()
    return report
