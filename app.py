"""CVCreater — Flask entry point.

Wiring only: the app object and its blueprints. This is the one file left at
the project root — everything else lives in a package:

    core/       config (paths, limits, demo bootstrap), db, store, tracker,
                util, demo_mode, personal_config
    ai/         gemini (the single Gemini call site) + generate (prompt builders)
    prompts/    the prompt texts as .md + their loader
    render/     documents (CV / Anschreiben / Projektliste HTML) + cv_layouts
    routes/     one blueprint per view
"""
from flask import Flask

from core import config, demo_mode
from routes import applications, generator, profile, projects, queue, settings

app = Flask(__name__)

for module in (generator, profile, projects, settings, applications, queue):
    app.register_blueprint(module.bp)

if config.DEMO_ACTIVE:
    print(f"[demo] DEMO_MODE active — using workspace {demo_mode.DEMO_WORK}")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
