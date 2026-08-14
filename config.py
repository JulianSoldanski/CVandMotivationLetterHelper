"""Paths, limits and the demo-workspace wiring.

Importing this module has side effects on purpose: it loads .env, points the
data paths at the demo workspace when DEMO_MODE is set, and makes sure the
SQLite schema exists. Every other module imports it, so that happens once and
before anything touches the disk.
"""
import os

from dotenv import load_dotenv

import db
import demo_mode

load_dotenv()

# Wire up the demo workspace BEFORE init_schema() so a DB created on first run
# lands in data/.demo/ instead of the real data/ dir.
DEMO_ACTIVE = demo_mode.bootstrap()
GEMINI_MODEL  = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
PROJECTS_FILE = demo_mode.projects_path()
PROFILE_FILE  = demo_mode.profile_path()
SETTINGS_FILE = demo_mode.settings_path()

db.init_schema()

JOB_POSTING_MAX = 50_000
JOB_URL_MAX = 500
JOB_QUEUE_NOTE_MAX  = 500
JOB_QUEUE_TITLE_MAX = 300

# Tracking-Parameter, die beim Hinzufügen zur Queue gestrippt werden, damit
# dieselbe Stelle nicht 3× drin landet, weil sie über verschiedene Quellen
# (LinkedIn-Ad, Google-Search, Newsletter) ankommt.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {
    "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid",
    "ref", "ref_src", "ref_url", "referrer", "source",
    "trk", "trkCampaign", "trackingId",
}
APPLICATION_STAGES = [
    "documents_created",
    "application_sent",
    "interview_1",
    "interview_2",
    "interview_3",
    "rejected",
]
CV_DIR            = os.path.join(os.path.dirname(__file__), "cvs")
ANSCHREIBEN_DIR   = os.path.join(os.path.dirname(__file__), "anschreiben")
PROJEKTLISTE_DIR  = os.path.join(os.path.dirname(__file__), "projektliste")
os.makedirs(CV_DIR, exist_ok=True)
os.makedirs(ANSCHREIBEN_DIR, exist_ok=True)
os.makedirs(PROJEKTLISTE_DIR, exist_ok=True)
