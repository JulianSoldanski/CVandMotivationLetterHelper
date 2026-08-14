"""CVCreater — Flask entry point.

Wiring only: the app object and its blueprints. Everything else lives in a
module next door:

    config.py     paths, limits, demo-workspace bootstrap
    gemini.py     the single Gemini call site
    store.py      profile / projects / settings on disk
    tracker.py    application logging
    generate.py   prompt builders
    render.py     CV / Anschreiben / Projektliste HTML
    db.py         SQLite access
    routes_*.py   one blueprint per view
"""
from flask import Flask

import config
import demo_mode
import routes_applications
import routes_generator
import routes_profile
import routes_projects
import routes_queue
import routes_settings

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
