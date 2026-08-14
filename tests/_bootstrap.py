"""Test bootstrap — redirects every data path into a throwaway temp dir.

Import order matters: ``db.DB_FILE`` and the ``app`` module-level path
constants are read at import time (``app.py`` calls ``db.init_schema()`` while
importing), so they have to be rebound *before* ``import app``. That is why
this module does its patching at import time rather than in a fixture.
"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

TMP = tempfile.mkdtemp(prefix="cvcreater-test-")

import db  # noqa: E402

db.DB_FILE = os.path.join(TMP, "test.db")

import app as app_module  # noqa: E402

app_module.PROFILE_FILE = os.path.join(TMP, "profile.json")
app_module.PROJECTS_FILE = os.path.join(TMP, "projects.json")
app_module.SETTINGS_FILE = os.path.join(TMP, "settings.json")

flask_app = app_module.app
flask_app.config["TESTING"] = True
