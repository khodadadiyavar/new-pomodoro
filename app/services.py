from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from app.config import AppConfig
from app.db import connect, init_db
from app.security import hash_password, verify_password


DATE_TO_WEEKDAY = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def to_iso_timestamp(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


class DeepWorkService:
    def __init__(self, config: AppConfig):
        self.config = config

    def init_db(self):
        init_db(self.config)

    def _connect(self):
        return connect(self.config)

    def _week_bounds(self, current_day: date):
        start_weekday = DATE_TO_WEEKDAY.get(self.config.week_starts_on, 0)
        offset = (current_day.weekday() - start_weekday) % 7
        week_start = current_day - timedelta(days=offset)
        week_end = week_start + timedelta(days=6)
        return week_start, week_end

    def _serialize_row(self, row):
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}

    def count_users(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        return int(row["count"])

    def get_user_by_id(self, user_id: int):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, email, is_admin, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return self._serialize_row(row)

    def bootstrap_admin(self, email: str, password: str):
        if self.count_users() > 0:
            raise ValueError("Bootstrap is only available before the first user exists.")

        now = to_iso_timestamp(utc_now())
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO users (email, password_hash, is_admin, created_at)
                VALUES (?, ?, 1, ?)
                RETURNING id, email, is_admin, created_at
                """,
                (email.strip().lower(), hash_password(password), now),
            ).fetchone()
        return self._serialize_row(row)

    def create_user(self, actor_user_id: int, email: str, password: str, is_admin: bool = False):
        actor = self.get_user_by_id(actor_user_id)
        if not actor or not actor["is_admin"]:
            raise PermissionError("Only admins can create users.")

        now = to_iso_timestamp(utc_now())
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO users (email, password_hash, is_admin, created_at)
                VALUES (?, ?, ?, ?)
                RETURNING id, email, is_admin, created_at
                """,
                (email.strip().lower(), hash_password(password), bool(is_admin), now),
            ).fetchone()
        return self._serialize_row(row)

    def list_users(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, email, is_admin, created_at FROM users ORDER BY email ASC"
            ).fetchall()
        return [self._serialize_row(row) for row in rows]

    def authenticate_user(self, email: str, password: str):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ?",
                (email.strip().lower(),),
            ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            raise ValueError("Invalid email or password.")
        return {
            "id": row["id"],
            "email": row["email"],
            "is_admin": row["is_admin"],
            "created_at": row["created_at"],
        }

    def create_goal(self, user_id: int, title: str, description: str):
        now = to_iso_timestamp(utc_now())
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO goals (user_id, title, description, status, created_at)
                VALUES (?, ?, ?, 'active', ?)
                RETURNING *
                """,
                (user_id, title.strip(), description.strip(), now),
            ).fetchone()
        return self._serialize_row(row)

    def list_goals(self, user_id: int, status: Optional[str] = None):
        query = "SELECT * FROM goals WHERE user_id = ?"
        params = [user_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END, created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._serialize_row(row) for row in rows]

    def get_goal(self, user_id: int, goal_id: int):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM goals WHERE id = ? AND user_id = ?",
                (goal_id, user_id),
            ).fetchone()
        return self._serialize_row(row)

    def update_goal_status(self, user_id: int, goal_id: int, status: str):
        if status not in {"active", "paused", "completed"}:
            raise ValueError("Invalid goal status.")
        completed_at = to_iso_timestamp(utc_now()) if status == "completed" else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE goals
                SET status = ?, completed_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (status, completed_at, goal_id, user_id),
            )
        return self.get_goal(user_id, goal_id)

    def add_milestone(self, user_id: int, goal_id: int, content: str, created_at: Optional[datetime] = None):
        timestamp = to_iso_timestamp(created_at or utc_now())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO milestones (user_id, goal_id, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, goal_id, content.strip(), timestamp),
            )

    def add_goal_note(self, user_id: int, goal_id: int, content: str, created_at: Optional[datetime] = None):
        timestamp = to_iso_timestamp(created_at or utc_now())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO goal_notes (user_id, goal_id, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, goal_id, content.strip(), timestamp),
            )

    def get_goal_detail(self, user_id: int, goal_id: int):
        goal = self.get_goal(user_id, goal_id)
        if not goal:
            return None

        with self._connect() as connection:
            sessions = connection.execute(
                """
                SELECT * FROM focus_sessions
                WHERE user_id = ? AND goal_id = ?
                ORDER BY started_at DESC
                """,
                (user_id, goal_id),
            ).fetchall()
            milestones = connection.execute(
                """
                SELECT * FROM milestones
                WHERE user_id = ? AND goal_id = ?
                ORDER BY created_at DESC
                """,
                (user_id, goal_id),
            ).fetchall()
            notes = connection.execute(
                """
                SELECT * FROM goal_notes
                WHERE user_id = ? AND goal_id = ?
                ORDER BY created_at DESC
                """,
                (user_id, goal_id),
            ).fetchall()
            total = connection.execute(
                """
                SELECT COALESCE(SUM(actual_minutes), 0) AS total_minutes
                FROM focus_sessions
                WHERE user_id = ? AND goal_id = ? AND state = 'completed'
                """,
                (user_id, goal_id),
            ).fetchone()

        return {
            "goal": goal,
            "total_minutes": int(total["total_minutes"]),
            "sessions": [self._serialize_row(row) for row in sessions],
            "milestones": [self._serialize_row(row) for row in milestones],
            "notes": [self._serialize_row(row) for row in notes],
        }

    def get_or_create_weekly_review(self, user_id: int, today: Optional[date] = None):
        current_day = today or utc_now().date()
        week_start, week_end = self._week_bounds(current_day)
        self.refresh_review_statuses(today=current_day)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM weekly_reviews
                WHERE user_id = ? AND week_start = ?
                """,
                (user_id, week_start.isoformat()),
            ).fetchone()
            if row:
                return self._serialize_row(row)

            now = to_iso_timestamp(utc_now())
            row = connection.execute(
                """
                INSERT INTO weekly_reviews (user_id, week_start, week_end, status, created_at)
                VALUES (?, ?, ?, 'open', ?)
                RETURNING *
                """,
                (user_id, week_start.isoformat(), week_end.isoformat(), now),
            ).fetchone()
        return self._serialize_row(row)

    def get_weekly_review(self, user_id: int, week_start: str):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM weekly_reviews
                WHERE user_id = ? AND week_start = ?
                """,
                (user_id, week_start),
            ).fetchone()
        return self._serialize_row(row)

    def refresh_review_statuses(self, today: Optional[date] = None):
        current_day = today or utc_now().date()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE weekly_reviews
                SET status = 'overdue'
                WHERE status = 'open' AND week_end < ?
                """,
                (current_day.isoformat(),),
            )

    def upsert_weekly_commitment(self, user_id: int, week_start: str, goal_id: int, target_hours: int):
        review = self.get_weekly_review(user_id, week_start)
        if not review:
            review = self.get_or_create_weekly_review(user_id, today=date.fromisoformat(week_start))

        target_minutes = int(target_hours) * 60
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO weekly_goal_commitments (weekly_review_id, goal_id, target_minutes)
                VALUES (?, ?, ?)
                ON CONFLICT(weekly_review_id, goal_id)
                DO UPDATE SET target_minutes = excluded.target_minutes
                """,
                (review["id"], goal_id, target_minutes),
            )

    def update_weekly_review(
        self,
        user_id: int,
        week_start: str,
        reflection: str,
        next_week_note: str,
        finalize: bool = False,
    ):
        review = self.get_weekly_review(user_id, week_start)
        if not review:
            raise ValueError("Weekly review not found.")

        finalized_at = to_iso_timestamp(utc_now()) if finalize else review["finalized_at"]
        status = "finalized" if finalize else review["status"]
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE weekly_reviews
                SET reflection = ?, next_week_note = ?, status = ?, finalized_at = ?
                WHERE id = ?
                """,
                (reflection.strip(), next_week_note.strip(), status, finalized_at, review["id"]),
            )
        return self.get_weekly_review(user_id, week_start)

    def list_weekly_commitments(self, user_id: int, week_start: str):
        review = self.get_weekly_review(user_id, week_start)
        if not review:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.*, g.title, g.status
                FROM weekly_goal_commitments c
                JOIN goals g ON g.id = c.goal_id
                WHERE c.weekly_review_id = ? AND g.user_id = ?
                ORDER BY g.title ASC
                """,
                (review["id"], user_id),
            ).fetchall()
        return [self._serialize_row(row) for row in rows]

    def _ensure_goal_owned(self, user_id: int, goal_id: int):
        goal = self.get_goal(user_id, goal_id)
        if not goal:
            raise ValueError("Goal not found.")
        return goal

    def get_active_session(self, user_id: int):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM focus_sessions
                WHERE user_id = ? AND state IN ('running', 'paused')
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return self._serialize_row(row)

    def start_session(
        self,
        user_id: int,
        goal_id: int,
        planned_minutes: int,
        started_at: Optional[datetime] = None,
    ):
        self._ensure_goal_owned(user_id, goal_id)
        if self.get_active_session(user_id):
            raise ValueError("Only one active session is allowed per user.")

        timestamp = started_at or utc_now()
        now = to_iso_timestamp(timestamp)
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO focus_sessions (
                    user_id, goal_id, state, planned_minutes, started_at, last_state_change_at
                )
                VALUES (?, ?, 'running', ?, ?, ?)
                RETURNING *
                """,
                (user_id, goal_id, planned_minutes, now, now),
            ).fetchone()
        return self._serialize_row(row)

    def _load_session(self, user_id: int, session_id: int):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM focus_sessions
                WHERE id = ? AND user_id = ?
                """,
                (session_id, user_id),
            ).fetchone()
        return self._serialize_row(row)

    def _elapsed_seconds_for_session(self, session, at_time: Optional[datetime] = None):
        if not session:
            return 0
        elapsed = int(session["elapsed_seconds"])
        if session["state"] == "running":
            current = at_time or utc_now()
            last_change = datetime.fromisoformat(session["last_state_change_at"])
            elapsed += max(0, int((current - last_change).total_seconds()))
        return elapsed

    def pause_session(self, user_id: int, session_id: int):
        session = self._load_session(user_id, session_id)
        if not session or session["state"] != "running":
            raise ValueError("Session is not running.")
        elapsed = self._elapsed_seconds_for_session(session)
        now = to_iso_timestamp(utc_now())
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE focus_sessions
                SET state = 'paused', elapsed_seconds = ?, last_state_change_at = ?
                WHERE id = ?
                """,
                (elapsed, now, session_id),
            )
        return self._load_session(user_id, session_id)

    def resume_session(self, user_id: int, session_id: int):
        session = self._load_session(user_id, session_id)
        if not session or session["state"] != "paused":
            raise ValueError("Session is not paused.")
        now = to_iso_timestamp(utc_now())
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE focus_sessions
                SET state = 'running', last_state_change_at = ?
                WHERE id = ?
                """,
                (now, session_id),
            )
        return self._load_session(user_id, session_id)

    def complete_session(
        self,
        user_id: int,
        session_id: int,
        ended_at: Optional[datetime] = None,
        actual_minutes: Optional[int] = None,
        note: str = "",
    ):
        session = self._load_session(user_id, session_id)
        if not session or session["state"] not in {"running", "paused"}:
            raise ValueError("Session is not active.")
        completed_at = ended_at or utc_now()
        elapsed_seconds = self._elapsed_seconds_for_session(session, at_time=completed_at)
        computed_minutes = max(1, round(elapsed_seconds / 60))
        final_minutes = int(actual_minutes or computed_minutes)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE focus_sessions
                SET state = 'completed',
                    actual_minutes = ?,
                    elapsed_seconds = ?,
                    ended_at = ?,
                    last_state_change_at = ?,
                    note = ?
                WHERE id = ?
                """,
                (
                    final_minutes,
                    elapsed_seconds,
                    to_iso_timestamp(completed_at),
                    to_iso_timestamp(completed_at),
                    note.strip(),
                    session_id,
                ),
            )
        return self._load_session(user_id, session_id)

    def abandon_session(self, user_id: int, session_id: int):
        session = self._load_session(user_id, session_id)
        if not session or session["state"] not in {"running", "paused"}:
            raise ValueError("Session is not active.")
        now = utc_now()
        elapsed_seconds = self._elapsed_seconds_for_session(session, at_time=now)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE focus_sessions
                SET state = 'abandoned',
                    elapsed_seconds = ?,
                    actual_minutes = 0,
                    ended_at = ?,
                    last_state_change_at = ?
                WHERE id = ?
                """,
                (
                    elapsed_seconds,
                    to_iso_timestamp(now),
                    to_iso_timestamp(now),
                    session_id,
                ),
            )
        return self._load_session(user_id, session_id)

    def get_weekly_scoreboard(self, user_id: int, week_start: str):
        review = self.get_weekly_review(user_id, week_start)
        if not review:
            return {
                "review": None,
                "goals": [],
                "total_target_minutes": 0,
                "total_actual_minutes": 0,
            }
        week_end = review["week_end"]
        with self._connect() as connection:
            goal_rows = connection.execute(
                """
                SELECT
                    g.id AS goal_id,
                    g.title,
                    g.status,
                    c.target_minutes,
                    COALESCE(a.actual_minutes, 0) AS actual_minutes
                FROM weekly_goal_commitments c
                JOIN goals g ON g.id = c.goal_id
                LEFT JOIN (
                    SELECT goal_id, SUM(actual_minutes) AS actual_minutes
                    FROM focus_sessions
                    WHERE user_id = ?
                      AND state = 'completed'
                      AND date(started_at) BETWEEN ? AND ?
                    GROUP BY goal_id
                ) a ON a.goal_id = g.id
                WHERE c.weekly_review_id = ? AND g.user_id = ?
                ORDER BY g.title ASC
                """,
                (user_id, week_start, week_end, review["id"], user_id),
            ).fetchall()

        goals = []
        total_target = 0
        total_actual = 0
        for row in goal_rows:
            target_minutes = int(row["target_minutes"])
            actual_minutes = int(row["actual_minutes"])
            total_target += target_minutes
            total_actual += actual_minutes
            goals.append(
                {
                    "goal_id": row["goal_id"],
                    "title": row["title"],
                    "status": row["status"],
                    "target_minutes": target_minutes,
                    "actual_minutes": actual_minutes,
                    "delta_minutes": actual_minutes - target_minutes,
                }
            )

        return {
            "review": review,
            "goals": goals,
            "total_target_minutes": total_target,
            "total_actual_minutes": total_actual,
        }

    def list_recent_milestones(self, user_id: int, limit: int = 6):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT m.*, g.title AS goal_title
                FROM milestones m
                JOIN goals g ON g.id = m.goal_id
                WHERE m.user_id = ?
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [self._serialize_row(row) for row in rows]

    def get_dashboard_data(self, user_id: int, today: Optional[date] = None):
        review = self.get_or_create_weekly_review(user_id, today=today)
        scoreboard = self.get_weekly_scoreboard(user_id, review["week_start"])
        overdue_reviews = []
        with self._connect() as connection:
            overdue_rows = connection.execute(
                """
                SELECT * FROM weekly_reviews
                WHERE user_id = ? AND status = 'overdue'
                ORDER BY week_start DESC
                LIMIT 3
                """,
                (user_id,),
            ).fetchall()
            active_goal_rows = connection.execute(
                """
                SELECT * FROM goals
                WHERE user_id = ? AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 8
                """,
                (user_id,),
            ).fetchall()
        overdue_reviews = [self._serialize_row(row) for row in overdue_rows]
        return {
            "review": review,
            "scoreboard": scoreboard,
            "active_goals": [self._serialize_row(row) for row in active_goal_rows],
            "recent_milestones": self.list_recent_milestones(user_id),
            "active_session": self.get_active_session(user_id),
            "overdue_reviews": overdue_reviews,
        }

    def get_history_data(self, user_id: int, weeks: int = 12):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM focus_sessions
                WHERE user_id = ? AND state = 'completed'
                ORDER BY started_at DESC
                """,
                (user_id,),
            ).fetchall()
        bucketed: Dict[str, int] = {}
        for row in rows:
            week_start, _ = self._week_bounds(date.fromisoformat(row["started_at"][:10]))
            bucketed.setdefault(week_start.isoformat(), 0)
            bucketed[week_start.isoformat()] += int(row["actual_minutes"])

        recent_weeks = sorted(bucketed.items(), reverse=True)[:weeks]
        recent_weeks.reverse()

        with self._connect() as connection:
            milestone_rows = connection.execute(
                """
                SELECT m.*, g.title AS goal_title
                FROM milestones m
                JOIN goals g ON g.id = m.goal_id
                WHERE m.user_id = ?
                ORDER BY m.created_at DESC
                LIMIT 20
                """,
                (user_id,),
            ).fetchall()
        return {
            "weekly_totals": [
                {"week_start": week_start, "total_minutes": total}
                for week_start, total in recent_weeks
            ],
            "milestones": [self._serialize_row(row) for row in milestone_rows],
        }
