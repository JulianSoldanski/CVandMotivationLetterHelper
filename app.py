"""CVCreater — Flask entry point.

Wiring only: the app object and its blueprints. Everything else lives in a
module next door:

    config.py     paths, limits, demo-workspace bootstrap
    gemini.py     the single Gemini call site
    store.py      profile / projects / settings on disk
    tracker.py    application logging
    generate.py   prompt builders
    prompts/      the prompt texts (.md) + their loader
    render.py     CV / Anschreiben / Projektliste HTML
    db.py         SQLite access
    routes_*.py   one blueprint per view
"""
from flask import Flask

from core import config

from core import demo_mode

from routes import applications as routes_applications

from routes import generator as routes_generator

from routes import profile as routes_profile

from routes import projects as routes_projects

from routes import queue as routes_queue

from routes import settings as routes_settings


app = Flask(__name__)

for module in (
    routes_generator,
    routes_profile,
    routes_projects,
    routes_settings,
    routes_applications,
    routes_queue,
):
    app.register_blueprint(module.bp)

if config.DEMO_ACTIVE:
    print(f"[demo] DEMO_MODE active — using workspace {demo_mode.DEMO_WORK}")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
