import io
import unittest
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
        self.assertIn("Weekly Focus", body)

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


if __name__ == "__main__":
    unittest.main()
