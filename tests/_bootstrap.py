"""Test bootstrap — redirects every data path into a throwaway temp dir.

Import order matters. `config` resolves the data paths and runs
`db.init_schema()` at import time, so `db.DB_FILE` has to be rebound before
`config` is imported, and the path constants right after — while `store` still
reads them through `config.<NAME>` on every call.
"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

TMP = tempfile.mkdtemp(prefix="cvcreater-test-")

import db  # noqa: E402

db.DB_FILE = os.path.join(TMP, "test.db")

import config  # noqa: E402

config.PROFILE_FILE = os.path.join(TMP, "profile.json")
config.PROJECTS_FILE = os.path.join(TMP, "projects.json")
config.SETTINGS_FILE = os.path.join(TMP, "settings.json")

import app as app_module  # noqa: E402

flask_app = app_module.app
flask_app.config["TESTING"] = True
