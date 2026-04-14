import json
from html import escape
from pathlib import Path
from urllib.parse import parse_qs

from app.config import AppConfig
from app.services import DeepWorkService
from app.security import read_session, sign_session


STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: AppConfig):
    service = DeepWorkService(config)
    service.init_db()

    def application(environ, start_response):
        method = environ["REQUEST_METHOD"].upper()
        path = environ.get("PATH_INFO", "/")
        form = parse_form(environ) if method == "POST" else {}
        cookie_header = parse_cookie(environ.get("HTTP_COOKIE", ""))
        current_user = load_current_user(service, config, cookie_header)

        if path.startswith("/static/"):
            return serve_static(path, start_response)

        if path == "/":
            if service.count_users() == 0:
                return redirect(start_response, "/bootstrap")
            if current_user:
                return redirect(start_response, "/dashboard")
            return redirect(start_response, "/login")

        if path == "/bootstrap":
            if service.count_users() > 0:
                return redirect(start_response, "/login")
            if method == "GET":
                return html_response(
                    start_response,
                    render_auth_page(
                        "Bootstrap Admin",
                        "Create the first admin account for this installation.",
                        "/bootstrap",
                        "Create admin account",
                    ),
                )
            try:
                user = service.bootstrap_admin(form.get("email", ""), form.get("password", ""))
            except ValueError as error:
                return html_response(
                    start_response,
                    render_auth_page(
                        "Bootstrap Admin",
                        str(error),
                        "/bootstrap",
                        "Create admin account",
                        error=True,
                    ),
                    status="400 Bad Request",
                )
            return redirect_with_session(start_response, "/dashboard", user["id"], config)

        if path == "/login":
            if method == "GET":
                return html_response(
                    start_response,
                    render_auth_page(
                        "Sign in",
                        "Local account login for this private installation.",
                        "/login",
                        "Sign in",
                    ),
                )
            try:
                user = service.authenticate_user(form.get("email", ""), form.get("password", ""))
            except ValueError as error:
                return html_response(
                    start_response,
                    render_auth_page(
                        "Sign in",
                        str(error),
                        "/login",
                        "Sign in",
                        error=True,
                    ),
                    status="401 Unauthorized",
                )
            return redirect_with_session(start_response, "/dashboard", user["id"], config)

        if path == "/logout" and method == "POST":
            headers = [
                ("Location", "/login"),
                ("Set-Cookie", "session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"),
            ]
            start_response("303 See Other", headers)
            return [b""]

        if not current_user:
            return redirect(start_response, "/login")

        if path == "/dashboard":
            data = service.get_dashboard_data(current_user["id"])
            return html_response(
                start_response,
                render_layout(
                    "Dashboard",
                    render_dashboard(data),
                    current_user,
                    "/dashboard",
                ),
            )

        if path == "/goals" and method == "GET":
            return html_response(
                start_response,
                render_layout(
                    "Goals",
                    render_goals_index(service.list_goals(current_user["id"])),
                    current_user,
                    "/goals",
                ),
            )

        if path == "/goals" and method == "POST":
            title = form.get("title", "").strip()
            if title:
                service.create_goal(current_user["id"], title, form.get("description", ""))
            return redirect(start_response, "/goals")

        if path.startswith("/goals/"):
            parts = [segment for segment in path.split("/") if segment]
            if len(parts) == 2 and method == "GET":
                goal_id = int(parts[1])
                detail = service.get_goal_detail(current_user["id"], goal_id)
                if not detail:
                    return not_found(start_response)
                return html_response(
                    start_response,
                    render_layout(
                        detail["goal"]["title"],
                        render_goal_detail(detail),
                        current_user,
                        "/goals",
                    ),
                )
            if len(parts) == 3 and method == "POST":
                goal_id = int(parts[1])
                action = parts[2]
                if action == "status":
                    service.update_goal_status(current_user["id"], goal_id, form.get("status", "active"))
                elif action == "milestones" and form.get("content", "").strip():
                    service.add_milestone(current_user["id"], goal_id, form["content"])
                elif action == "notes" and form.get("content", "").strip():
                    service.add_goal_note(current_user["id"], goal_id, form["content"])
                return redirect(start_response, f"/goals/{goal_id}")

        if path == "/focus":
            dashboard = service.get_dashboard_data(current_user["id"])
            return html_response(
                start_response,
                render_layout(
                    "Focus",
                    render_focus_page(
                        current_user,
                        service.list_goals(current_user["id"], status="active"),
                        dashboard["active_session"],
                        config,
                    ),
                    current_user,
                    "/focus",
                    extra_scripts=['<script src="/static/focus.js"></script>'],
                ),
            )

        if path == "/weekly-review" and method == "GET":
            review = service.get_or_create_weekly_review(current_user["id"])
            commitments = service.list_weekly_commitments(current_user["id"], review["week_start"])
            scoreboard = service.get_weekly_scoreboard(current_user["id"], review["week_start"])
            body = render_weekly_review(
                review,
                commitments,
                scoreboard,
                service.list_goals(current_user["id"]),
            )
            return html_response(
                start_response,
                render_layout("Weekly Review", body, current_user, "/weekly-review"),
            )

        if path == "/weekly-review/commitments" and method == "POST":
            review = service.get_or_create_weekly_review(current_user["id"])
            for goal in service.list_goals(current_user["id"]):
                key = f"goal-{goal['id']}"
                raw_value = form.get(key, "").strip()
                if raw_value:
                    service.upsert_weekly_commitment(
                        current_user["id"], review["week_start"], goal["id"], int(raw_value)
                    )
            return redirect(start_response, "/weekly-review")

        if path == "/weekly-review/finalize" and method == "POST":
            review = service.get_or_create_weekly_review(current_user["id"])
            service.update_weekly_review(
                current_user["id"],
                review["week_start"],
                form.get("reflection", ""),
                form.get("next_week_note", ""),
                finalize=form.get("finalize") == "1",
            )
            return redirect(start_response, "/weekly-review")

        if path == "/history":
            return html_response(
                start_response,
                render_layout(
                    "History",
                    render_history(service.get_history_data(current_user["id"])),
                    current_user,
                    "/history",
                ),
            )

        if path == "/admin/users":
            if not current_user["is_admin"]:
                return forbidden(start_response)
            if method == "POST":
                service.create_user(
                    current_user["id"],
                    form.get("email", ""),
                    form.get("password", ""),
                    is_admin=form.get("is_admin") == "1",
                )
                return redirect(start_response, "/admin/users")
            return html_response(
                start_response,
                render_layout(
                    "User Management",
                    render_admin_users(service.list_users()),
                    current_user,
                    "/admin/users",
                ),
            )

        if path == "/api/sessions/start" and method == "POST":
            session = service.start_session(
                current_user["id"],
                int(form["goal_id"]),
                int(form.get("planned_minutes", config.focus_minutes)),
            )
            payload = {
                "session": session,
                "goal": service.get_goal(current_user["id"], int(form["goal_id"])),
            }
            return json_response(start_response, payload)

        if path.startswith("/api/sessions/") and method == "POST":
            parts = [segment for segment in path.split("/") if segment]
            session_id = int(parts[2])
            action = parts[3]
            if action == "pause":
                session = service.pause_session(current_user["id"], session_id)
            elif action == "resume":
                session = service.resume_session(current_user["id"], session_id)
            elif action == "complete":
                session = service.complete_session(
                    current_user["id"],
                    session_id,
                    note=form.get("note", ""),
                )
            elif action == "abandon":
                session = service.abandon_session(current_user["id"], session_id)
            else:
                return not_found(start_response)
            return json_response(start_response, {"session": session})

        return not_found(start_response)

    return application


def parse_form(environ):
    content_length = int(environ.get("CONTENT_LENGTH", "0") or 0)
    body = environ["wsgi.input"].read(content_length).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def parse_cookie(cookie_header):
    cookies = {}
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        cookies[key] = value
    return cookies


def load_current_user(service, config, cookies):
    session_value = cookies.get("session")
    if not session_value:
        return None
    user_id = read_session(session_value, config.secret_key)
    if not user_id:
        return None
    return service.get_user_by_id(user_id)


def serve_static(path, start_response):
    file_path = STATIC_DIR / path.split("/static/", 1)[1]
    if not file_path.exists():
        return not_found(start_response)
    content_type = "text/plain; charset=utf-8"
    if file_path.suffix == ".css":
        content_type = "text/css; charset=utf-8"
    elif file_path.suffix == ".js":
        content_type = "application/javascript; charset=utf-8"
    start_response("200 OK", [("Content-Type", content_type)])
    return [file_path.read_bytes()]


def redirect(start_response, location):
    start_response("302 Found", [("Location", location)])
    return [b""]


def redirect_with_session(start_response, location, user_id, config):
    headers = [
        ("Location", location),
        (
            "Set-Cookie",
            f"session={sign_session(user_id, config.secret_key)}; Path=/; HttpOnly; SameSite=Lax",
        ),
    ]
    start_response("303 See Other", headers)
    return [b""]


def html_response(start_response, html, status="200 OK"):
    start_response(status, [("Content-Type", "text/html; charset=utf-8")])
    return [html.encode("utf-8")]


def json_response(start_response, payload, status="200 OK"):
    start_response(status, [("Content-Type", "application/json; charset=utf-8")])
    return [json.dumps(payload).encode("utf-8")]


def not_found(start_response):
    return html_response(start_response, "<h1>Not Found</h1>", status="404 Not Found")


def forbidden(start_response):
    return html_response(start_response, "<h1>Forbidden</h1>", status="403 Forbidden")


def minutes_to_hours_label(minutes):
    hours = minutes / 60
    return f"{hours:.1f}h"


def render_layout(title, content, user, active_path, extra_scripts=None):
    extra_scripts = extra_scripts or []
    nav_links = [
        ("/dashboard", "Dashboard"),
        ("/goals", "Goals"),
        ("/focus", "Focus"),
        ("/weekly-review", "Weekly Review"),
        ("/history", "History"),
    ]
    if user["is_admin"]:
        nav_links.append(("/admin/users", "Users"))

    nav_html = "".join(
        f'<a class="nav-link {"is-active" if href == active_path else ""}" href="{href}">{label}</a>'
        for href, label in nav_links
    )
    scripts = "".join(extra_scripts)
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)} · Deep Work 4DX</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <div class="background-orb background-orb-left"></div>
    <div class="background-orb background-orb-right"></div>
    <div class="shell">
      <aside class="sidebar">
        <div>
          <p class="eyebrow">Deep Work 4DX</p>
          <h1 class="brand-title">Focused execution, weekly accountability.</h1>
        </div>
        <nav class="nav">{nav_html}</nav>
        <div class="sidebar-footer">
          <div class="user-chip">{escape(user["email"])}</div>
          <form method="POST" action="/logout">
            <button class="ghost-button" type="submit">Sign out</button>
          </form>
        </div>
      </aside>
      <main class="content">
        <header class="page-header">
          <div>
            <p class="eyebrow">Private self-hosted deep work</p>
            <h2>{escape(title)}</h2>
          </div>
        </header>
        {content}
      </main>
    </div>
    {scripts}
  </body>
</html>"""


def render_auth_page(title, subtitle, action, button_label, error=False):
    tone_class = "auth-copy auth-copy-error" if error else "auth-copy"
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)} · Deep Work 4DX</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body class="auth-body">
    <div class="auth-shell">
      <section class="auth-panel auth-panel-hero">
        <p class="eyebrow">Deep Work 4DX</p>
        <h1>Build a weekly scoreboard around real focused work.</h1>
        <p>{escape(subtitle)}</p>
      </section>
      <section class="auth-panel auth-panel-form">
        <h2>{escape(title)}</h2>
        <p class="{tone_class}">{escape(subtitle)}</p>
        <form method="POST" action="{action}" class="stack">
          <label>
            <span>Email</span>
            <input type="email" name="email" required />
          </label>
          <label>
            <span>Password</span>
            <input type="password" name="password" required />
          </label>
          <button class="primary-button" type="submit">{escape(button_label)}</button>
        </form>
      </section>
    </div>
  </body>
</html>"""


def render_dashboard(data):
    scoreboard = data["scoreboard"]
    total_target = scoreboard["total_target_minutes"]
    total_actual = scoreboard["total_actual_minutes"]
    progress_ratio = 0 if total_target == 0 else min(1, total_actual / total_target)
    goals_html = ""
    for goal in scoreboard["goals"]:
        target = max(goal["target_minutes"], 1)
        ratio = min(1, goal["actual_minutes"] / target)
        goals_html += f"""
        <article class="metric-card">
          <div class="metric-card-header">
            <h3>{escape(goal["title"])}</h3>
            <span>{minutes_to_hours_label(goal["actual_minutes"])} / {minutes_to_hours_label(goal["target_minutes"])}</span>
          </div>
          <div class="progress">
            <div class="progress-bar" style="width:{ratio * 100:.0f}%"></div>
          </div>
          <p class="muted">Status: {escape(goal["status"])} · Delta {minutes_to_hours_label(goal["delta_minutes"])}</p>
        </article>
        """
    if not goals_html:
        goals_html = '<article class="metric-card"><h3>No weekly commitments yet</h3><p class="muted">Set target hours in Weekly Review to turn goals into a scoreboard.</p></article>'

    milestones_html = "".join(
        f"<li><strong>{escape(item['goal_title'])}</strong><span>{escape(item['content'])}</span></li>"
        for item in data["recent_milestones"]
    ) or "<li><span>No milestones recorded yet.</span></li>"

    overdue_html = "".join(
        f"<li>Week of {escape(review['week_start'])} is overdue.</li>"
        for review in data["overdue_reviews"]
    ) or "<li>No overdue reviews.</li>"

    active_session_html = ""
    if data["active_session"]:
        active_session_html = f"""
        <article class="hero-card hero-card-warning">
          <p class="eyebrow">Active focus session</p>
          <h3>Resume your current session</h3>
          <p>You already have a {escape(data["active_session"]["state"])} session in progress.</p>
          <a class="primary-button inline-button" href="/focus">Open focus view</a>
        </article>
        """

    return f"""
    <section class="dashboard-grid">
      <article class="hero-card">
        <p class="eyebrow">Weekly Focus</p>
        <h3>{minutes_to_hours_label(total_actual)} logged against {minutes_to_hours_label(total_target)} committed</h3>
        <div class="progress progress-hero">
          <div class="progress-bar" style="width:{progress_ratio * 100:.0f}%"></div>
        </div>
        <p class="muted">The dashboard stays anchored to this week’s commitments instead of all-time busyness.</p>
        <div class="button-row">
          <a class="primary-button inline-button" href="/focus">Start focus session</a>
          <a class="secondary-button inline-button" href="/weekly-review">Review commitments</a>
        </div>
      </article>
      {active_session_html}
      <section class="card-stack">
        <article class="panel">
          <div class="panel-header"><h3>Goal scoreboard</h3></div>
          {goals_html}
        </article>
        <article class="panel">
          <div class="panel-header"><h3>Recent milestones</h3></div>
          <ul class="activity-list">{milestones_html}</ul>
        </article>
        <article class="panel">
          <div class="panel-header"><h3>Review cadence</h3></div>
          <ul class="activity-list">{overdue_html}</ul>
        </article>
      </section>
    </section>
    """


def render_goals_index(goals):
    cards = "".join(
        f"""
        <article class="goal-card">
          <div>
            <p class="eyebrow">{escape(goal['status'])}</p>
            <h3>{escape(goal['title'])}</h3>
            <p class="muted">{escape(goal['description'] or 'No description yet.')}</p>
          </div>
          <a class="secondary-button inline-button" href="/goals/{goal['id']}">Open</a>
        </article>
        """
        for goal in goals
    ) or '<article class="goal-card"><h3>No goals yet</h3><p class="muted">Create a goal, then commit weekly hours against it.</p></article>'

    return f"""
    <section class="two-column">
      <article class="panel">
        <div class="panel-header"><h3>Create goal</h3></div>
        <form method="POST" action="/goals" class="stack">
          <label><span>Title</span><input type="text" name="title" required /></label>
          <label><span>Description</span><textarea name="description" rows="4"></textarea></label>
          <button class="primary-button" type="submit">Add goal</button>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Goal library</h3></div>
        <div class="goal-list">{cards}</div>
      </article>
    </section>
    """


def render_goal_detail(detail):
    goal = detail["goal"]
    milestones = "".join(
        f"<li><span>{escape(item['created_at'][:10])}</span><strong>{escape(item['content'])}</strong></li>"
        for item in detail["milestones"]
    ) or "<li><span>No milestones yet.</span></li>"
    notes = "".join(
        f"<li><span>{escape(item['created_at'][:10])}</span><strong>{escape(item['content'])}</strong></li>"
        for item in detail["notes"]
    ) or "<li><span>No notes yet.</span></li>"
    sessions = "".join(
        f"<li><span>{escape(item['started_at'][:16].replace('T', ' '))}</span><strong>{item['state']}</strong><span>{minutes_to_hours_label(item['actual_minutes'])}</span></li>"
        for item in detail["sessions"][:10]
    ) or "<li><span>No sessions yet.</span></li>"

    return f"""
    <section class="goal-detail-grid">
      <article class="hero-card">
        <p class="eyebrow">{escape(goal['status'])}</p>
        <h3>{escape(goal['title'])}</h3>
        <p>{escape(goal['description'] or 'No description yet.')}</p>
        <p class="muted">Completed deep work: {minutes_to_hours_label(detail['total_minutes'])}</p>
        <div class="button-row">
          <a class="primary-button inline-button" href="/focus">Start session</a>
          <form method="POST" action="/goals/{goal['id']}/status">
            <select name="status">
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="completed">Completed</option>
            </select>
            <button class="secondary-button inline-button" type="submit">Update status</button>
          </form>
        </div>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Add milestone</h3></div>
        <form method="POST" action="/goals/{goal['id']}/milestones" class="stack">
          <label><span>Milestone</span><input type="text" name="content" required /></label>
          <button class="primary-button" type="submit">Record milestone</button>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Add note</h3></div>
        <form method="POST" action="/goals/{goal['id']}/notes" class="stack">
          <label><span>Note</span><textarea name="content" rows="4" required></textarea></label>
          <button class="primary-button" type="submit">Save note</button>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Milestones</h3></div>
        <ul class="activity-list">{milestones}</ul>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Notes</h3></div>
        <ul class="activity-list">{notes}</ul>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Recent sessions</h3></div>
        <ul class="activity-list">{sessions}</ul>
      </article>
    </section>
    """


def render_focus_page(user, goals, active_session, config):
    goal_options = "".join(
        f'<option value="{goal["id"]}">{escape(goal["title"])}</option>'
        for goal in goals
    )
    active_payload = json.dumps(active_session or {})
    return f"""
    <section class="focus-layout" data-focus-root data-active-session='{escape(active_payload)}'>
      <article class="hero-card focus-card">
        <p class="eyebrow">Deep work timer</p>
        <h3 id="focus-state-label">Ready for a focus block</h3>
        <div class="focus-timer" id="focus-timer">25:00</div>
        <p class="muted">Run the session here. Completed focus blocks are written back to the weekly scoreboard automatically.</p>
        <div class="button-row">
          <button class="primary-button inline-button" id="start-session-button">Start session</button>
          <button class="secondary-button inline-button" id="pause-session-button" type="button">Pause</button>
          <button class="secondary-button inline-button" id="resume-session-button" type="button">Resume</button>
          <button class="ghost-button inline-button" id="complete-session-button" type="button">Complete</button>
          <button class="ghost-button inline-button" id="abandon-session-button" type="button">Abandon</button>
        </div>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Session setup</h3></div>
        <div class="stack">
          <label>
            <span>Goal</span>
            <select id="goal-id">{goal_options}</select>
          </label>
          <label>
            <span>Focus minutes</span>
            <input id="planned-minutes" type="number" min="5" step="5" value="{config.focus_minutes}" />
          </label>
          <label>
            <span>Session note</span>
            <textarea id="session-note" rows="4" placeholder="What moved forward in this session?"></textarea>
          </label>
          <div class="focus-presets">
            <span class="preset-chip">Focus {config.focus_minutes}m</span>
            <span class="preset-chip">Short break {config.short_break_minutes}m</span>
            <span class="preset-chip">Long break {config.long_break_minutes}m</span>
          </div>
          <p class="muted" id="focus-status-message">One active focus session is allowed per user.</p>
        </div>
      </article>
    </section>
    """


def render_weekly_review(review, commitments, scoreboard, goals):
    commitment_lookup = {item["goal_id"]: item for item in commitments}
    rows = ""
    for goal in goals:
        current_hours = ""
        if goal["id"] in commitment_lookup:
            current_hours = str(int(commitment_lookup[goal["id"]]["target_minutes"] / 60))
        rows += f"""
        <tr>
          <td>{escape(goal['title'])}</td>
          <td>{escape(goal['status'])}</td>
          <td><input type="number" min="0" step="1" name="goal-{goal['id']}" value="{current_hours}" /></td>
        </tr>
        """

    scoreboard_rows = "".join(
        f"""
        <article class="metric-card">
          <div class="metric-card-header">
            <h3>{escape(goal['title'])}</h3>
            <span>{minutes_to_hours_label(goal['actual_minutes'])} / {minutes_to_hours_label(goal['target_minutes'])}</span>
          </div>
          <p class="muted">Delta: {minutes_to_hours_label(goal['delta_minutes'])}</p>
        </article>
        """
        for goal in scoreboard["goals"]
    ) or '<article class="metric-card"><h3>No committed goals</h3><p class="muted">Add target hours below.</p></article>'

    return f"""
    <section class="two-column">
      <article class="panel">
        <div class="panel-header"><h3>Commit this week</h3></div>
        <p class="muted">Week of {escape(review['week_start'])} to {escape(review['week_end'])}. Status: {escape(review['status'])}.</p>
        <form method="POST" action="/weekly-review/commitments" class="stack">
          <table class="review-table">
            <thead><tr><th>Goal</th><th>Status</th><th>Target hours</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
          <button class="primary-button" type="submit">Save commitments</button>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Scoreboard</h3></div>
        <div class="metric-stack">{scoreboard_rows}</div>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Reflection and carry-forward</h3></div>
        <form method="POST" action="/weekly-review/finalize" class="stack">
          <label><span>Reflection</span><textarea name="reflection" rows="5">{escape(review['reflection'])}</textarea></label>
          <label><span>Plan for next week</span><textarea name="next_week_note" rows="5">{escape(review['next_week_note'])}</textarea></label>
          <div class="button-row">
            <button class="secondary-button" type="submit">Save notes</button>
            <button class="primary-button" type="submit" name="finalize" value="1">Finalize review</button>
          </div>
        </form>
      </article>
    </section>
    """


def render_history(data):
    max_minutes = max([item["total_minutes"] for item in data["weekly_totals"]] or [1])
    bars = "".join(
        f"""
        <div class="history-bar-group">
          <div class="history-bar" style="height:{max(16, (item['total_minutes'] / max_minutes) * 220):.0f}px"></div>
          <span>{escape(item['week_start'])}</span>
          <strong>{minutes_to_hours_label(item['total_minutes'])}</strong>
        </div>
        """
        for item in data["weekly_totals"]
    ) or "<p class='muted'>No completed sessions yet.</p>"
    milestones = "".join(
        f"<li><span>{escape(item['created_at'][:10])}</span><strong>{escape(item['goal_title'])}</strong><span>{escape(item['content'])}</span></li>"
        for item in data["milestones"]
    ) or "<li><span>No milestones yet.</span></li>"

    return f"""
    <section class="two-column">
      <article class="panel">
        <div class="panel-header"><h3>Weekly totals</h3></div>
        <div class="history-bars">{bars}</div>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Milestone history</h3></div>
        <ul class="activity-list">{milestones}</ul>
      </article>
    </section>
    """


def render_admin_users(users):
    rows = "".join(
        f"<li><strong>{escape(user['email'])}</strong><span>{'Admin' if user['is_admin'] else 'Member'}</span></li>"
        for user in users
    )
    return f"""
    <section class="two-column">
      <article class="panel">
        <div class="panel-header"><h3>Create user</h3></div>
        <form method="POST" action="/admin/users" class="stack">
          <label><span>Email</span><input type="email" name="email" required /></label>
          <label><span>Password</span><input type="password" name="password" required /></label>
          <label class="checkbox-row"><input type="checkbox" name="is_admin" value="1" />Make admin</label>
          <button class="primary-button" type="submit">Create user</button>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header"><h3>Accounts</h3></div>
        <ul class="activity-list">{rows}</ul>
      </article>
    </section>
    """
