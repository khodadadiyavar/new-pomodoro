import io
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode

from app.config import AppConfig
from app.services import DeepWorkService
from app.web import create_app


def run_wsgi_request(app, path, method="GET", form_data=None, cookie=None):
    body = urlencode(form_data or {}).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.StringIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
    }
    if cookie:
        environ["HTTP_COOKIE"] = cookie

    captured = {"status": None, "headers": []}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    response = b"".join(app(environ, start_response))
    return captured["status"], dict(captured["headers"]), response.decode("utf-8")


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "deepwork.db"
        self.config = AppConfig(
            database_path=str(db_path),
            secret_key="test-secret",
            week_starts_on="monday",
        )
        self.app = create_app(self.config)
        self.service = DeepWorkService(self.config)

    def tearDown(self):
        self.temp_dir.cleanup()

    def login_cookie(self, email="admin@example.com", password="password"):
        status, headers, _ = run_wsgi_request(
            self.app,
            "/login",
            method="POST",
            form_data={"email": email, "password": password},
        )
        self.assertEqual(status, "303 See Other")
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_bootstrap_redirects_to_dashboard_after_creating_first_admin(self):
        status, _, _ = run_wsgi_request(self.app, "/")
        self.assertEqual(status, "302 Found")

        status, headers, _ = run_wsgi_request(
            self.app,
            "/bootstrap",
            method="POST",
            form_data={"email": "admin@example.com", "password": "password"},
        )
        self.assertEqual(status, "303 See Other")
        self.assertEqual(headers["Location"], "/dashboard")
        self.assertIn("session=", headers["Set-Cookie"])

        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, body = run_wsgi_request(self.app, "/dashboard", cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertIn("Weekly focus", body)

    def test_users_cannot_open_another_users_goal_detail_page(self):
        self.service.init_db()
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        other = self.service.create_user(admin["id"], "other@example.com", "password")
        private_goal = self.service.create_goal(admin["id"], "Private goal", "")

        status, headers, _ = run_wsgi_request(
            self.app,
            "/login",
            method="POST",
            form_data={"email": "other@example.com", "password": "password"},
        )
        self.assertEqual(status, "303 See Other")
        cookie = headers["Set-Cookie"].split(";", 1)[0]

        status, _, _ = run_wsgi_request(self.app, f"/goals/{private_goal['id']}", cookie=cookie)
        self.assertEqual(status, "404 Not Found")

    def test_admin_user_creation_shows_inline_error_for_duplicate_email(self):
        self.service.init_db()
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        self.service.create_user(admin["id"], "other@example.com", "password")

        status, headers, _ = run_wsgi_request(
            self.app,
            "/login",
            method="POST",
            form_data={"email": "admin@example.com", "password": "password"},
        )
        self.assertEqual(status, "303 See Other")
        cookie = headers["Set-Cookie"].split(";", 1)[0]

        status, _, body = run_wsgi_request(
            self.app,
            "/admin/users",
            method="POST",
            form_data={"email": "other@example.com", "password": "another-password"},
            cookie=cookie,
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("already exists", body)

    def test_admin_user_creation_requires_email_and_password(self):
        self.service.init_db()
        self.service.bootstrap_admin("admin@example.com", "password")

        status, headers, _ = run_wsgi_request(
            self.app,
            "/login",
            method="POST",
            form_data={"email": "admin@example.com", "password": "password"},
        )
        self.assertEqual(status, "303 See Other")
        cookie = headers["Set-Cookie"].split(";", 1)[0]

        blank_email_status, _, blank_email_body = run_wsgi_request(
            self.app,
            "/admin/users",
            method="POST",
            form_data={"email": "", "password": "password"},
            cookie=cookie,
        )
        self.assertEqual(blank_email_status, "400 Bad Request")
        self.assertIn("Email is required", blank_email_body)

        blank_password_status, _, blank_password_body = run_wsgi_request(
            self.app,
            "/admin/users",
            method="POST",
            form_data={"email": "teammate@example.com", "password": ""},
            cookie=cookie,
        )
        self.assertEqual(blank_password_status, "400 Bad Request")
        self.assertIn("Password is required", blank_password_body)

    def test_theme_selection_sets_cookie_and_renders_active_theme(self):
        self.service.init_db()
        self.service.bootstrap_admin("admin@example.com", "password")

        status, headers, _ = run_wsgi_request(
            self.app,
            "/login",
            method="POST",
            form_data={"email": "admin@example.com", "password": "password"},
        )
        self.assertEqual(status, "303 See Other")
        session_cookie = headers["Set-Cookie"].split(";", 1)[0]

        status, headers, _ = run_wsgi_request(
            self.app,
            "/theme",
            method="POST",
            form_data={"theme": "dark", "return_to": "/dashboard"},
            cookie=session_cookie,
        )
        self.assertEqual(status, "303 See Other")
        self.assertEqual(headers["Location"], "/dashboard")
        self.assertIn("theme=dark", headers["Set-Cookie"])

        combined_cookie = f"{session_cookie}; {headers['Set-Cookie'].split(';', 1)[0]}"
        status, _, body = run_wsgi_request(self.app, "/dashboard", cookie=combined_cookie)
        self.assertEqual(status, "200 OK")
        self.assertIn('data-theme="dark"', body)
        self.assertIn('value="dark"', body)

    def test_theme_control_is_hidden_on_login_and_bootstrap(self):
        status, _, bootstrap_body = run_wsgi_request(self.app, "/bootstrap", cookie="theme=dark")
        self.assertEqual(status, "200 OK")
        self.assertIn('data-theme="dark"', bootstrap_body)
        self.assertNotIn('action="/theme"', bootstrap_body)
        self.assertNotIn('name="theme"', bootstrap_body)

        self.service.init_db()
        self.service.bootstrap_admin("admin@example.com", "password")

        status, _, login_body = run_wsgi_request(self.app, "/login", cookie="theme=dark")
        self.assertEqual(status, "200 OK")
        self.assertIn('data-theme="dark"', login_body)
        self.assertNotIn('action="/theme"', login_body)
        self.assertNotIn('name="theme"', login_body)

        session_cookie = self.login_cookie()
        status, headers, _ = run_wsgi_request(
            self.app,
            "/theme",
            method="POST",
            form_data={"theme": "dark", "return_to": "/dashboard"},
            cookie=session_cookie,
        )
        self.assertEqual(status, "303 See Other")
        combined_cookie = f"{session_cookie}; {headers['Set-Cookie'].split(';', 1)[0]}"

        status, _, dashboard_body = run_wsgi_request(self.app, "/dashboard", cookie=combined_cookie)
        self.assertEqual(status, "200 OK")
        self.assertIn('data-theme="dark"', dashboard_body)
        self.assertIn('action="/theme"', dashboard_body)
        self.assertIn('name="theme"', dashboard_body)

    def test_paused_session_can_be_resumed_without_server_error(self):
        self.service.init_db()
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(admin["id"], "Ship v1", "Deliver it")
        cookie = self.login_cookie()

        status, _, start_body = run_wsgi_request(
            self.app,
            "/api/sessions/start",
            method="POST",
            form_data={"goal_id": str(goal["id"]), "planned_minutes": "25"},
            cookie=cookie,
        )
        self.assertEqual(status, "200 OK")
        start_payload = json.loads(start_body)
        session_id = start_payload["session"]["id"]

        status, _, pause_body = run_wsgi_request(
            self.app,
            f"/api/sessions/{session_id}/pause",
            method="POST",
            cookie=cookie,
        )
        self.assertEqual(status, "200 OK")
        pause_payload = json.loads(pause_body)
        self.assertEqual(pause_payload["session"]["state"], "paused")

        status, _, paused_status_body = run_wsgi_request(self.app, "/api/session-status", cookie=cookie)
        self.assertEqual(status, "200 OK")
        paused_status_payload = json.loads(paused_status_body)
        self.assertEqual(paused_status_payload["session"]["id"], session_id)
        self.assertEqual(paused_status_payload["session"]["state"], "paused")
        self.assertEqual(paused_status_payload["goal"]["title"], "Ship v1")

        status, _, resume_body = run_wsgi_request(
            self.app,
            f"/api/sessions/{session_id}/resume",
            method="POST",
            cookie=cookie,
        )
        self.assertEqual(status, "200 OK")
        resume_payload = json.loads(resume_body)
        self.assertEqual(resume_payload["session"]["id"], session_id)
        self.assertEqual(resume_payload["session"]["state"], "running")

        status, _, resumed_status_body = run_wsgi_request(self.app, "/api/session-status", cookie=cookie)
        self.assertEqual(status, "200 OK")
        resumed_status_payload = json.loads(resumed_status_body)
        self.assertEqual(resumed_status_payload["session"]["state"], "running")
        self.assertEqual(resumed_status_payload["goal"]["title"], "Ship v1")

    def test_dashboard_and_goals_page_render_live_session_chrome(self):
        self.service.init_db()
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(admin["id"], "Ship v1", "Deliver it")
        self.service.start_session(admin["id"], goal["id"], 25)
        cookie = self.login_cookie()

        status, _, dashboard_body = run_wsgi_request(self.app, "/dashboard", cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertIn("data-live-session-bar", dashboard_body)
        self.assertIn("data-current-focus-widget", dashboard_body)
        self.assertIn("Ship v1", dashboard_body)
        self.assertIn("Session is running", dashboard_body)
        self.assertIn("This week's goal scoreboard", dashboard_body)
        self.assertIn("Milestone momentum", dashboard_body)

        status, _, goals_body = run_wsgi_request(self.app, "/goals", cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertIn("data-live-session-bar", goals_body)
        self.assertIn("Ship v1", goals_body)
        self.assertNotIn("data-current-focus-widget", goals_body)

    def test_focus_page_uses_stop_and_discard_controls(self):
        self.service.init_db()
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        self.service.create_goal(admin["id"], "Ship v1", "Deliver it")
        cookie = self.login_cookie()

        status, _, body = run_wsgi_request(self.app, "/focus", cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertIn('id="stop-session-button"', body)
        self.assertIn(">Stop</button>", body)
        self.assertIn('id="discard-session-button"', body)
        self.assertIn(">Discard</button>", body)
        self.assertNotIn('id="complete-session-button"', body)
        self.assertNotIn('id="abandon-session-button"', body)

    def test_focus_page_does_not_seed_stale_active_session_payload(self):
        self.service.init_db()
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(admin["id"], "Ship v1", "Deliver it")
        self.service.start_session(
            admin["id"],
            goal["id"],
            25,
            started_at=datetime.utcnow() - timedelta(minutes=30),
        )
        cookie = self.login_cookie()

        status, _, body = run_wsgi_request(self.app, "/focus", cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertIn("data-focus-root", body)
        self.assertIn("data-active-session='{}'", body)
        self.assertNotIn('"state": "running"', body)

    def test_session_status_reports_auto_finished_transition(self):
        self.service.init_db()
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(admin["id"], "Ship v1", "Deliver it")
        self.service.start_session(
            admin["id"],
            goal["id"],
            25,
            started_at=datetime.utcnow() - timedelta(minutes=30),
        )
        cookie = self.login_cookie()

        status, _, body = run_wsgi_request(self.app, "/api/session-status", cookie=cookie)
        self.assertEqual(status, "200 OK")
        payload = json.loads(body)
        self.assertIsNone(payload["session"])
        self.assertEqual(payload["goal"]["title"], "Ship v1")
        self.assertTrue(payload["just_completed"])
        self.assertEqual(payload["ended_reason"], "auto_finished")

        status, _, follow_up_body = run_wsgi_request(self.app, "/api/session-status", cookie=cookie)
        self.assertEqual(status, "200 OK")
        follow_up_payload = json.loads(follow_up_body)
        self.assertFalse(follow_up_payload["just_completed"])
        self.assertIsNone(follow_up_payload["ended_reason"])

    def test_stale_stop_request_returns_json_conflict_instead_of_crashing(self):
        self.service.init_db()
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(admin["id"], "Ship v1", "Deliver it")
        session = self.service.start_session(
            admin["id"],
            goal["id"],
            25,
            started_at=datetime.utcnow() - timedelta(minutes=30),
        )
        cookie = self.login_cookie()

        status, headers, body = run_wsgi_request(
            self.app,
            f"/api/sessions/{session['id']}/stop",
            method="POST",
            form_data={"note": "Too late"},
            cookie=cookie,
        )
        self.assertEqual(status, "409 Conflict")
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        payload = json.loads(body)
        self.assertEqual(payload["error"], "Session is not active.")

    def test_goal_detail_renders_new_milestones_and_notes(self):
        self.service.init_db()
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(admin["id"], "Ship v1", "Deliver it")

        status, headers, _ = run_wsgi_request(
            self.app,
            "/login",
            method="POST",
            form_data={"email": "admin@example.com", "password": "password"},
        )
        self.assertEqual(status, "303 See Other")
        cookie = headers["Set-Cookie"].split(";", 1)[0]

        milestone_status, _, _ = run_wsgi_request(
            self.app,
            f"/goals/{goal['id']}/milestones",
            method="POST",
            form_data={"content": "Finished the API contract"},
            cookie=cookie,
        )
        self.assertEqual(milestone_status, "302 Found")

        note_status, _, _ = run_wsgi_request(
            self.app,
            f"/goals/{goal['id']}/notes",
            method="POST",
            form_data={"content": "Need one more review pass"},
            cookie=cookie,
        )
        self.assertEqual(note_status, "302 Found")

        status, _, body = run_wsgi_request(self.app, f"/goals/{goal['id']}", cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertIn("Finished the API contract", body)
        self.assertIn("Need one more review pass", body)

    def test_goal_detail_renders_session_history_with_duration(self):
        self.service.init_db()
        admin = self.service.bootstrap_admin("admin@example.com", "password")
        goal = self.service.create_goal(admin["id"], "Ship v1", "Deliver it")
        session = self.service.start_session(
            admin["id"],
            goal["id"],
            60,
            started_at=datetime.utcnow() - timedelta(hours=2),
        )
        self.service.complete_session(
            admin["id"],
            session["id"],
            ended_at=datetime.utcnow() - timedelta(hours=1),
            actual_minutes=55,
            note="Closed the launch checklist and captured follow-up notes",
        )
        self.service.add_milestone(
            admin["id"],
            goal["id"],
            "Final QA pass complete",
            created_at=datetime.utcnow() - timedelta(minutes=45),
        )
        cookie = self.login_cookie()

        status, _, body = run_wsgi_request(self.app, f"/goals/{goal['id']}", cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertIn("Milestone timeline", body)
        self.assertIn("Session history", body)
        self.assertIn("Duration", body)
        self.assertIn("0.9h focused", body)
        self.assertIn("Closed the launch checklist and captured follow-up notes", body)


if __name__ == "__main__":
    unittest.main()
