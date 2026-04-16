import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import AppConfig
from app.services import DeepWorkService


class DeepWorkServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "deepwork.db"
        self.config = AppConfig(
            database_path=str(db_path),
            secret_key="test-secret",
            week_starts_on="monday",
        )
        self.service = DeepWorkService(self.config)
        self.service.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_bootstrap_admin_and_authentication(self):
        admin = self.service.bootstrap_admin("admin@example.com", "correct horse battery staple")

        self.assertTrue(admin["is_admin"])
        authenticated = self.service.authenticate_user(
            "admin@example.com", "correct horse battery staple"
        )
        self.assertEqual(authenticated["id"], admin["id"])

        with self.assertRaises(ValueError):
            self.service.bootstrap_admin("second@example.com", "password")

    def test_goal_commitments_and_completed_sessions_roll_up_to_weekly_scoreboard(self):
        user = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(user["id"], "Ship v1", "Deliver the first release")

        review = self.service.get_or_create_weekly_review(user["id"], today=date(2026, 4, 14))
        self.service.upsert_weekly_commitment(
            user["id"], review["week_start"], goal["id"], target_minutes=300
        )

        started_at = datetime(2026, 4, 14, 9, 0, 0)
        session = self.service.start_session(
            user["id"], goal["id"], planned_minutes=25, started_at=started_at
        )
        self.service.complete_session(
            user["id"],
            session["id"],
            ended_at=started_at + timedelta(minutes=50),
            actual_minutes=50,
            note="Finished the landing page copy",
        )

        scoreboard = self.service.get_weekly_scoreboard(user["id"], review["week_start"])

        self.assertEqual(scoreboard["total_target_minutes"], 300)
        self.assertEqual(scoreboard["total_actual_minutes"], 50)
        self.assertEqual(scoreboard["goals"][0]["goal_id"], goal["id"])
        self.assertEqual(scoreboard["goals"][0]["target_minutes"], 300)
        self.assertEqual(scoreboard["goals"][0]["actual_minutes"], 50)
        self.assertEqual(scoreboard["goals"][0]["delta_minutes"], -250)

    def test_abandoned_sessions_do_not_count_as_completed_deep_work(self):
        user = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(user["id"], "Read deeply", "Study technical books")
        review = self.service.get_or_create_weekly_review(user["id"], today=date(2026, 4, 14))
        self.service.upsert_weekly_commitment(
            user["id"], review["week_start"], goal["id"], target_minutes=180
        )

        session = self.service.start_session(
            user["id"],
            goal["id"],
            planned_minutes=25,
            started_at=datetime(2026, 4, 14, 10, 0, 0),
        )
        self.service.abandon_session(user["id"], session["id"])

        scoreboard = self.service.get_weekly_scoreboard(user["id"], review["week_start"])

        self.assertEqual(scoreboard["total_actual_minutes"], 0)
        self.assertEqual(scoreboard["goals"][0]["actual_minutes"], 0)

    def test_stop_session_records_duration_in_goal_history(self):
        user = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(user["id"], "Ship v1", "Deliver it")
        session = self.service.start_session(
            user["id"],
            goal["id"],
            planned_minutes=25,
            started_at=datetime(2026, 4, 15, 9, 0, 0),
        )

        stopped = self.service.stop_session(
            user["id"],
            session["id"],
            ended_at=datetime(2026, 4, 15, 9, 18, 0),
            note="Stopped early after a good pass",
        )
        detail = self.service.get_goal_detail(user["id"], goal["id"])

        self.assertEqual(stopped["state"], "completed")
        self.assertEqual(detail["sessions"][0]["id"], session["id"])
        self.assertEqual(detail["sessions"][0]["actual_minutes"], 18)

    def test_discarded_session_is_not_returned_in_goal_history_or_scoreboard(self):
        user = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(user["id"], "Read deeply", "Study")
        review = self.service.get_or_create_weekly_review(user["id"], today=date(2026, 4, 15))
        self.service.upsert_weekly_commitment(user["id"], review["week_start"], goal["id"], 3)
        session = self.service.start_session(
            user["id"],
            goal["id"],
            planned_minutes=25,
            started_at=datetime(2026, 4, 15, 10, 0, 0),
        )

        self.service.discard_session(user["id"], session["id"])
        detail = self.service.get_goal_detail(user["id"], goal["id"])
        scoreboard = self.service.get_weekly_scoreboard(user["id"], review["week_start"])

        self.assertEqual(detail["sessions"], [])
        self.assertEqual(scoreboard["goals"][0]["actual_minutes"], 0)

    def test_reconcile_active_session_auto_completes_expired_running_session(self):
        user = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(user["id"], "Ship v1", "Deliver it")
        reconcile_time = datetime(2026, 4, 15, 8, 30, 0)
        expected_completion_time = datetime(2026, 4, 15, 8, 25, 0)
        session = self.service.start_session(
            user["id"],
            goal["id"],
            planned_minutes=25,
            started_at=datetime(2026, 4, 15, 8, 0, 0),
        )

        active = self.service.get_active_session(
            user["id"],
            now=reconcile_time,
        )
        detail = self.service.get_goal_detail(user["id"], goal["id"])

        self.assertIsNone(active)
        self.assertEqual(detail["sessions"][0]["id"], session["id"])
        self.assertEqual(detail["sessions"][0]["state"], "completed")
        self.assertEqual(detail["sessions"][0]["actual_minutes"], 25)
        self.assertEqual(detail["sessions"][0]["elapsed_seconds"], 25 * 60)
        self.assertEqual(detail["sessions"][0]["ended_at"], expected_completion_time.isoformat())

    def test_user_data_is_isolated(self):
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        other = self.service.create_user(admin["id"], "other@example.com", "password")

        own_goal = self.service.create_goal(admin["id"], "Private goal", "")
        other_goal = self.service.create_goal(other["id"], "Other goal", "")

        self.assertEqual([goal["id"] for goal in self.service.list_goals(admin["id"])], [own_goal["id"]])
        self.assertEqual([goal["id"] for goal in self.service.list_goals(other["id"])], [other_goal["id"]])
        self.assertIsNone(self.service.get_goal(admin["id"], other_goal["id"]))

    def test_previous_open_reviews_become_overdue_after_the_week_ends(self):
        user = self.service.bootstrap_admin("admin@example.com", "password")
        prior_review = self.service.get_or_create_weekly_review(user["id"], today=date(2026, 4, 6))

        self.service.refresh_review_statuses(today=date(2026, 4, 14))
        refreshed = self.service.get_weekly_review(user["id"], prior_review["week_start"])

        self.assertEqual(refreshed["status"], "overdue")


if __name__ == "__main__":
    unittest.main()
