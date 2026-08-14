"""Smoke tests: every route answers, and the document renderers produce HTML.

Not a correctness suite — it exists so a refactor that deletes ~1200 lines
can't silently break a route or a renderer. Gemini is never called: the tests
either hit AI-free routes or stub the generation helpers.

Run with:  python3 -m unittest discover -s tests -v
"""
import json
import unittest
from unittest import mock

from _bootstrap import app_module, flask_app  # rebinds every data path first
import db as db_module


class RouteSmokeTest(unittest.TestCase):
    """AI-free routes answer 200 and return the shape the frontend expects."""

    def setUp(self):
        self.c = flask_app.test_client()

    def test_index_renders(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"<html", r.data.lower())

    def test_layouts(self):
        r = self.c.get("/layouts")
        self.assertEqual(r.status_code, 200)
        ids = {item["id"] for item in r.get_json()}
        self.assertEqual(ids, {"modern", "classic", "sidebar"})

    def test_mode(self):
        r = self.c.get("/mode")
        self.assertEqual(r.status_code, 200)
        self.assertIn("demo", r.get_json())

    def test_profile_shape(self):
        r = self.c.get("/profile")
        self.assertEqual(r.status_code, 200)
        for key in ("experience", "education", "hard_skills", "soft_skills", "languages"):
            self.assertIn(key, r.get_json())

    def test_list_endpoints_return_lists(self):
        for path in ("/projects", "/applications", "/queue"):
            with self.subTest(path=path):
                r = self.c.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertIsInstance(r.get_json(), list)

    def test_settings(self):
        r = self.c.get("/settings")
        self.assertEqual(r.status_code, 200)
        self.assertIn("style_example", r.get_json())

    def test_bookmarklet_install_page(self):
        r = self.c.get("/queue/install")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"javascript:", r.data)


class BadBodyTest(unittest.TestCase):
    """A malformed/missing JSON body must not produce a 500."""

    def setUp(self):
        self.c = flask_app.test_client()

    def test_post_without_body(self):
        for path in ("/fetch-job", "/render", "/save", "/projects"):
            with self.subTest(path=path):
                r = self.c.post(path, data="", content_type="application/json")
                self.assertLess(
                    r.status_code, 500,
                    f"{path} returned {r.status_code} on an empty body",
                )


class RenderTest(unittest.TestCase):
    """The renderers turn generated content into a full HTML document."""

    CV_CONTENT = {
        "profile": "Kurzprofil.",
        "experience": [],
        "education": [],
        "projects": [],
        "skills": {"Tech & Methoden": "Python, Flask"},
    }
    ANSCHREIBEN_CONTENT = {
        "company_name": "ACME GmbH",
        "city_date": "Berlin, 1. Januar 2026",
        "subject": "Bewerbung",
        "greeting": "Sehr geehrte Damen und Herren,",
        "paragraphs": ["Absatz eins.", "Absatz zwei."],
    }

    def setUp(self):
        self.c = flask_app.test_client()

    def test_cv_all_layouts_both_languages(self):
        for layout in ("modern", "classic", "sidebar"):
            for language in ("de", "en"):
                with self.subTest(layout=layout, language=language):
                    r = self.c.post("/render", json={
                        "doc_type": "cv",
                        "content": self.CV_CONTENT,
                        "layout": layout,
                        "language": language,
                    })
                    self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
                    html = r.get_json()["html"]
                    self.assertIn("<!DOCTYPE html>", html)
                    self.assertIn("Kurzprofil.", html)

    def test_anschreiben(self):
        r = self.c.post("/render", json={
            "doc_type": "anschreiben",
            "content": self.ANSCHREIBEN_CONTENT,
            "language": "de",
        })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        html = r.get_json()["html"]
        self.assertIn("ACME GmbH", html)
        self.assertIn("Absatz zwei.", html)

    def test_unknown_doc_type_is_400(self):
        r = self.c.post("/render", json={"doc_type": "nope", "content": {}})
        self.assertEqual(r.status_code, 400)


class GenerateTest(unittest.TestCase):
    """/generate wires the pieces together — with Gemini stubbed out."""

    def setUp(self):
        self.c = flask_app.test_client()

    def test_generate_returns_documents(self):
        cv = {"profile": "P", "experience": [], "education": [], "projects": [], "skills": {}}
        anschreiben = {"company_name": "ACME", "paragraphs": ["A"]}

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
             mock.patch.object(app_module, "generate_cv_content", return_value=cv), \
             mock.patch.object(app_module, "generate_anschreiben_content", return_value=anschreiben), \
             mock.patch.object(app_module, "generate_job_summary", return_value={
                 "company_does": "X", "searching_for": [], "technologies": []}):
            r = self.c.post("/generate", json={
                "job_posting": "Wir suchen einen Entwickler.",
                "company": "ACME",
                "position": "Entwickler",
                "language": "de",
                "doc_type": "both",
            })

        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertEqual(data["cv_content"], cv)
        self.assertEqual(data["anschreiben_content"], anschreiben)
        self.assertIn("job_summary", data)

    def test_generate_without_posting_is_400(self):
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            r = self.c.post("/generate", json={"job_posting": "  "})
        self.assertEqual(r.status_code, 400)


class ApplicationLifecycleTest(unittest.TestCase):
    """Create → advance stage → delete, straight through the DB layer."""

    def setUp(self):
        self.c = flask_app.test_client()

    def test_lifecycle(self):
        r = self.c.post("/applications", json={
            "company": "ACME", "position": "Entwickler", "stage": "documents_created",
        })
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        app_id = r.get_json()["id"]

        r = self.c.put(f"/applications/{app_id}", json={"stage": "application_sent"})
        self.assertEqual(r.status_code, 200)
        entry = r.get_json()
        self.assertEqual(entry["stage"], "application_sent")
        self.assertIsNotNone(entry["applied_at"], "applied_at is set on first send")
        self.assertEqual([e["stage"] for e in entry["stage_history"]],
                         ["documents_created", "application_sent"])

        r = self.c.get(f"/applications/{app_id}")
        self.assertEqual(r.status_code, 200)

        r = self.c.delete(f"/applications/{app_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get(f"/applications/{app_id}").status_code, 404)

    def test_invalid_stage_is_400(self):
        r = self.c.post("/applications", json={"company": "X", "stage": "bogus"})
        self.assertEqual(r.status_code, 400)


class ProjectCrudTest(unittest.TestCase):
    def setUp(self):
        self.c = flask_app.test_client()

    def test_crud_roundtrip(self):
        r = self.c.post("/projects", json={"title": "Testprojekt", "description": "Beschreibung"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        pid = r.get_json()["id"]

        r = self.c.put(f"/projects/{pid}", json={"title": "Umbenannt", "description": "Beschreibung"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["title"], "Umbenannt")

        self.assertEqual(self.c.delete(f"/projects/{pid}").status_code, 200)
        self.assertNotIn(pid, [p["id"] for p in self.c.get("/projects").get_json()])


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.c = flask_app.test_client()

    def test_add_dedupes_tracking_params(self):
        base = "https://example.com/job/42"
        r = self.c.post("/queue", json={"url": base + "?utm_source=newsletter#top"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        item = r.get_json()["item"]
        self.assertEqual(item["url"], base, "tracking params and fragment are stripped")

        r = self.c.post("/queue", json={"url": base + "?gclid=abc"})
        self.assertTrue(r.get_json()["duplicate"], "same posting collapses onto one row")

        self.assertEqual(self.c.delete(f"/queue/{item['id']}").status_code, 200)

    def test_add_without_url_is_400(self):
        self.assertEqual(self.c.post("/queue", json={}).status_code, 400)


class LegacyDatabaseTest(unittest.TestCase):
    """A DB written by the pre-refactor app must still open and read."""

    def test_orphan_columns_are_ignored(self):
        import os
        import sqlite3
        import tempfile

        legacy = os.path.join(tempfile.mkdtemp(prefix="cvcreater-legacy-"), "legacy.db")
        original = db_module.DB_FILE
        try:
            db_module.DB_FILE = legacy
            db_module.init_schema()
            # Re-create the columns the old schema had, then write a row through them.
            with sqlite3.connect(legacy) as conn:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(applications)")}
                for col in ("company_info", "fit_score"):
                    if col not in cols:
                        conn.execute(f"ALTER TABLE applications ADD COLUMN {col} TEXT")
                qcols = {r[1] for r in conn.execute("PRAGMA table_info(job_queue)")}
                for col in ("company_info", "fit_score", "enriched_at", "error"):
                    if col not in qcols:
                        conn.execute(f"ALTER TABLE job_queue ADD COLUMN {col} TEXT")

            db_module.upsert_application({
                "id": "legacy01", "company": "Alt AG", "position": "Dev",
                "stage": "documents_created", "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            })
            with sqlite3.connect(legacy) as conn:
                conn.execute(
                    "UPDATE applications SET fit_score = ?, company_info = ? WHERE id = ?",
                    (json.dumps({"score": 80}), json.dumps({"hq": "Berlin"}), "legacy01"),
                )

            entries = db_module.list_applications()
            self.assertEqual([e["id"] for e in entries], ["legacy01"])
            self.assertEqual(entries[0]["company"], "Alt AG")

            db_module.add_queue_item("q1", "https://example.com/x", "T", "", "2026-01-01T00:00:00")
            self.assertEqual(len(db_module.list_queue()), 1)
        finally:
            db_module.DB_FILE = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
