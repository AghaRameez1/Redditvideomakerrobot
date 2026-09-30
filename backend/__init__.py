"""Web backend: accounts, the studio API, and the frontend pages."""
import sqlite3

import click
from flask import Flask, redirect
from werkzeug.middleware.proxy_fix import ProxyFix

from engine.paths import ROOT

from . import cleanup, config, db
from .admin import bp as admin_bp
from .api import bp as api_bp
from .auth import bp as auth_bp
from .connections import bp as connections_bp
from .library import bp as library_bp
from .security import ROLES, check_same_origin, current_user, page_login_required, page_role_required


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(ROOT / "frontend"), static_url_path="/static")
    app.config.update(config.load())
    if app.config["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # real https + client IP

    db.init(app)
    app.before_request(check_same_origin)
    for blueprint in (auth_bp, api_bp, library_bp, connections_bp, admin_bp):
        app.register_blueprint(blueprint)

    @app.get("/login")
    def login_page():
        return redirect("/") if current_user() else app.send_static_file("login.html")

    @app.get("/")
    def home_page():
        """Signed in: the studio. Otherwise: the public home page with sign-up and sign-in links."""
        return app.send_static_file("index.html" if current_user() else "landing.html")

    @app.get("/videos")
    @page_login_required
    def library_page():
        return app.send_static_file("library.html")

    @app.get("/settings")
    @page_login_required
    def settings_page():
        return app.send_static_file("settings.html")

    @app.get("/admin")
    @page_role_required("manager")
    def admin_page():
        return app.send_static_file("admin.html")

    @app.cli.command("make-admin")
    @click.argument("email")
    @click.option("--role", type=click.Choice(ROLES), default="admin", help="Role to give (default: admin).")
    @click.option("--remove", is_flag=True, help="Make them a plain user again.")
    def make_admin(email, role, remove):
        """Give an existing account a role: flask --app app make-admin you@example.com"""
        role = "user" if remove else role
        with sqlite3.connect(app.config["DATABASE_PATH"]) as conn:
            changed = conn.execute("UPDATE users SET role = ? WHERE email = ?", (role, email.strip())).rowcount
        if not changed:
            raise click.ClickException(f"No account with the email {email}. Sign up first, then run this again.")
        click.echo(f"{email} is now {'an' if role == 'admin' else 'a'} {role}.")

    @app.cli.command("cleanup")
    @click.option("--hours", type=int, help="Override the admin page setting for this run.")
    def cleanup_command(hours):
        """Remove files of posted videos (for cron): flask --app app cleanup"""
        if hours is None:
            result = cleanup.run_now(app)
            if not result["ran"]:
                raise click.ClickException("Auto-clean is off. Turn it on in Admin, or pass --hours.")
            removed = result["removed"]
        else:
            removed = cleanup.run(app.config["DATABASE_PATH"], hours)
        click.echo(f"Removed {removed} posted video file(s).")

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if app.config["PRODUCTION"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return resp

    return app
