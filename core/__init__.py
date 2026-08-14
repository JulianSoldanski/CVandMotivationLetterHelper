"""Foundation: paths, storage, and the helpers everything else builds on.

Deliberately empty — importing `core` must not pull in `core.config`, which
has import-time side effects (loads .env, wires the demo workspace, creates
the SQLite schema). The tests rebind `core.db.DB_FILE` before `core.config`
runs, and that only works while this file imports nothing.
"""
