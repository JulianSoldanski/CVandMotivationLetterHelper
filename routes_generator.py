"""Routes for the generator view: fetch a posting, generate, render, export.
"""
import os
import re

import requests as http_requests
from bs4 import BeautifulSoup
from flask import Blueprint, jsonify, make_response, render_template, request

import config
from cv_layouts import LAYOUTS
import demo_mode
from gemini import _generate, _call_gemini_json, call_gemini
from generate import (
    generate_anschreiben_content, generate_cv_content, generate_job_summary
)
from render import render_anschreiben_html, render_cv_html
from store import load_projects
from tracker import log_application

bp = Blueprint("generator", __name__)


@bp.route("/")
def index():
    # The entire frontend (HTML + CSS + JS) lives inline in this template.
    # Without no-store, browsers reuse the cached copy across template edits
    # which manifests as "the new feature I just shipped is invisible in the
    # UI". For a single-user local dev app the re-fetch cost is trivial.
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store"
    return resp


def fetch_job_posting(url: str, timeout: int = 10) -> str:
    """Fetch + clean a job-posting HTML page into plain text.

    Raises on network/HTTP errors; trims to 12k chars to stay within Gemini
    context budgets. Shared by /fetch-job, queue-add scoring, etc.
    """
    resp = http_requests.get(url, timeout=timeout, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    })
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    cleaned = "\n".join(lines)
    if len(cleaned) > 12000:
        cleaned = cleaned[:12000] + "\n[...]"
    return cleaned


@bp.route("/fetch-job", methods=["POST"])
def fetch_job():
    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "Keine URL angegeben."}), 400
    try:
        return jsonify({"text": fetch_job_posting(url)})
    except Exception as e:
        return jsonify({"error": f"Konnte URL nicht laden: {str(e)}"}), 500


@bp.route("/layouts", methods=["GET"])
def get_layouts():
    return jsonify([{"id": k, "name": v["name"], "style": v["style"]} for k, v in LAYOUTS.items()])


@bp.route("/mode", methods=["GET"])
def get_mode():
    """Tiny endpoint so the frontend can show a "DEMO" badge when the app
    was started with DEMO_MODE=1. The frontend polls this once on load."""
    return jsonify({"demo": demo_mode.is_demo_mode()})


@bp.route("/test-connection", methods=["GET"])
def test_connection():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"ok": False, "error": "GEMINI_API_KEY nicht gesetzt"}), 500
    try:
        reply = _generate("Say: OK", 10)
        return jsonify({"ok": True, "model": config.GEMINI_MODEL, "response": (reply or "").strip()})
    except Exception as e:
        return jsonify({"ok": False, "model": config.GEMINI_MODEL, "error": str(e)}), 500


@bp.route("/generate", methods=["POST"])
def generate():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt. Prüfe deine .env Datei."}), 500

    data         = request.get_json(silent=True) or {}
    job_posting  = data.get("job_posting", "").strip()
    if not job_posting:
        return jsonify({"error": "Bitte Stellenausschreibung einfügen."}), 400

    company         = data.get("company", "").strip()
    position        = data.get("position", "").strip()
    contact         = data.get("contact", "Sehr geehrte Damen und Herren").strip()
    city            = data.get("city", "Berlin").strip()
    language        = data.get("language", "de")
    doc_type        = data.get("doc_type", "both")
    custom_notes    = data.get("custom_notes", "").strip()
    layout          = data.get("layout", "modern")
    company_address = data.get("company_address", "").strip()

    projects = load_projects()
    result   = {"layout_used": resolved_layout, "job_posting": job_posting}

    try:
        if doc_type in ("cv", "both"):
            result["cv_content"] = generate_cv_content(
                job_posting, company, position, language, custom_notes, projects
            )
        if doc_type in ("anschreiben", "both"):
            result["anschreiben_content"] = generate_anschreiben_content(
                job_posting, company, position, contact, city, language, custom_notes, projects,
                company_address=company_address
            )
        result["job_summary"] = generate_job_summary(job_posting, language)
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {str(e)}"}), 500

    job_url = (data.get("job_url") or "").strip()
    try:
        tracked_seconds = int(data.get("tracked_seconds") or 0)
    except (TypeError, ValueError):
        tracked_seconds = 0
    logged = log_application(
        company, position, job_posting,
        job_url=job_url,
        cv_content          = result.get("cv_content"),
        anschreiben_content = result.get("anschreiben_content"),
        layout_used         = resolved_layout,
        language            = language,
        tracked_seconds     = tracked_seconds,
    )
    if logged:
        result["application"] = logged

    return jsonify(result)


@bp.route("/render", methods=["POST"])
def render_doc():
    data     = request.get_json(silent=True) or {}
    doc_type = data.get("doc_type", "cv")
    language = data.get("language", "de")
    projects = load_projects()

    try:
        if doc_type == "cv":
            html = render_cv_html(data.get("content", {}), data.get("layout", "modern"), language, projects)
        elif doc_type == "anschreiben":
            html = render_anschreiben_html(data.get("content", {}), language)
        else:
            return jsonify({"error": "Unbekannter doc_type"}), 400
    except Exception as e:
        return jsonify({"error": f"Render-Fehler: {str(e)}"}), 500

    return jsonify({"html": html})


@bp.route("/save", methods=["POST"])
def save_doc():
    data     = request.get_json(silent=True) or {}
    doc_type = data.get("doc_type", "cv")
    filename = data.get("filename", "document.html")
    html     = data.get("html", "")

    if not html:
        return jsonify({"error": "Kein Inhalt."}), 400

    # Sanitise filename — keep only safe chars
    safe = re.sub(r'[^\w\-_\.]', '_', filename)
    if not safe.endswith(".html"):
        safe = safe.rsplit(".", 1)[0] + ".html"

    folder = {
        "anschreiben":  config.ANSCHREIBEN_DIR,
        "projektliste": config.PROJEKTLISTE_DIR,
    }.get(doc_type, config.CV_DIR)
    path   = os.path.join(folder, safe)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return jsonify({"ok": True, "path": path, "filename": safe})


@bp.route("/extract-fields", methods=["POST"])
def extract_fields():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500
    data        = request.get_json(silent=True) or {}
    job_posting = (data.get("job_posting") or "").strip()
    if not job_posting:
        return jsonify({"error": "Kein Text angegeben."}), 400

    prompt = f"""Extrahiere folgende Informationen aus dieser Stellenausschreibung. Falls eine Information nicht vorhanden ist, gib null zurück.

STELLENAUSSCHREIBUNG:
{job_posting[:6000]}

Gib ein JSON-Objekt zurück:
{{
  "company": "Firmenname oder null",
  "position": "Genaue Stellenbezeichnung oder null",
  "contact": "Persönliche Anrede falls Name bekannt z.B. 'Sehr geehrte Frau Müller', sonst 'Sehr geehrte Damen und Herren'",
  "city": "Stadt des Unternehmensstandorts oder null",
  "company_address": "Vollständige Postanschrift mit Straße, PLZ und Stadt — nur wenn explizit in der Ausschreibung genannt, sonst null"
}}
"""
    try:
        result = _call_gemini_json(prompt, 512)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Fehler: {str(e)}"}), 500


@bp.route("/improve-text", methods=["POST"])
def improve_text():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500
    data        = request.get_json(silent=True) or {}
    text        = (data.get("text") or "").strip()
    instruction = (data.get("instruction") or "").strip()
    if not text or not instruction:
        return jsonify({"error": "Text und Anweisung erforderlich."}), 400

    prompt = f"""Du bist ein professioneller Bewerbungsschreiber. Überarbeite den folgenden Absatz eines Anschreibens basierend auf der Anweisung.

ORIGINAL-ABSATZ:
{text}

ANWEISUNG:
{instruction}

Regeln:
- Gib NUR den überarbeiteten Absatz zurück, ohne Erklärungen oder Anführungszeichen
- Behalte Stil und Länge ähnlich, außer die Anweisung sagt etwas anderes
- Keine neuen Fakten erfinden
"""
    try:
        result = call_gemini(prompt, 1024)
        return jsonify({"text": result})
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {str(e)}"}), 500
