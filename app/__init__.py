import os

import click
from flask import Flask, jsonify, redirect, url_for
from flask.cli import with_appcontext
from werkzeug.exceptions import HTTPException

from .api import api_bp
from .db import close_session, get_engine, init_engine
from .models import Base
from .ui import ui_bp


def create_app(test_config=None):
    app = Flask(__name__)

    if test_config is not None:
        app.config.from_mapping(test_config)
    else:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required to start the app.")
        app.config.from_mapping(
            DATABASE_URL=database_url,
            JSON_SORT_KEYS=False,
        )

    init_engine(app.config["DATABASE_URL"])
    app.teardown_appcontext(close_session)
    app.register_blueprint(api_bp)
    app.register_blueprint(ui_bp)

    @app.route("/")
    def root():
        return redirect(url_for("ui.index"))

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        response = jsonify(error=error.description)
        response.status_code = error.code
        return response

    @click.command("init-db")
    @with_appcontext
    def init_db_command():
        Base.metadata.create_all(bind=get_engine())
        click.echo("Database initialized.")

    app.cli.add_command(init_db_command)

    return app
