"""Writing-style settings, style analysis and CV-PDF import.
"""
import os

from flask import Blueprint, jsonify, request

from gemini import _call_gemini_json, call_gemini
from store import load_settings, save_settings

bp = Blueprint("settings", __name__)


@bp.route("/settings", methods=["GET"])
def get_settings():
    return jsonify(load_settings())


@bp.route("/settings", methods=["PUT"])
def update_settings():
    data     = request.get_json(silent=True) or {}
    settings = load_settings()
    for field in ("style_example", "style_analysis"):
        if isinstance(data.get(field), str):
            settings[field] = data[field].strip()
    save_settings(settings)
    return jsonify(settings)


@bp.route("/analyze-style", methods=["POST"])
def analyze_style():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500
    data    = request.get_json(silent=True) or {}
    example = (data.get("example") or "").strip()
    if not example:
        return jsonify({"error": "Beispiel-Text ist leer."}), 400

    # The analysis is the instruction layer: always English, language-agnostic,
    # so it can be applied to both German and English generation. The example
    # itself may be in either language.
    prompt = f"""Analyze the writing style of the example cover letter below and describe it in English, precisely enough that another AI can imitate this style later without copying the content. The example may be in German or English — describe the style itself, which carries over regardless of the language a letter is later written in.

EXAMPLE TEXT:
\"\"\"
{example[:6000]}
\"\"\"

Return 6–10 bullet points covering these aspects (where recognizable):
- Tone (formal ↔ casual, direct ↔ reserved, confident ↔ modest)
- Sentence structure (length, active/passive, parataxis/hypotaxis)
- Word choice (jargon, anglicisms, industry terms, deliberately avoided filler phrases)
- Structural patterns (opening, line of argument, closing)
- Recurring rhetorical devices or quirks

Format: plain markdown bullet list (\"- …\"), no preamble or closing remark, no salutation to me.
"""
    try:
        analysis = call_gemini(prompt, 1024).strip()
        return jsonify({"analysis": analysis})
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {str(e)}"}), 500


@bp.route("/parse-cv-pdf", methods=["POST"])
def parse_cv_pdf():
    """Extract text from an uploaded CV PDF and ask Gemini to structure it
    into the same `cv_content` JSON shape that /generate produces.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500

    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "Keine Datei hochgeladen."}), 400
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Bitte eine PDF-Datei hochladen."}), 400

    try:
        from pypdf import PdfReader
    except ImportError:
        return jsonify({"error": "pypdf nicht installiert (pip install pypdf)."}), 500

    try:
        reader = PdfReader(upload.stream)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n".join(pages).strip()
    except Exception as e:
        return jsonify({"error": f"PDF konnte nicht gelesen werden: {e}"}), 400

    if not text:
        return jsonify({"error": "Aus der PDF konnte kein Text extrahiert werden."}), 400

    # Self-contained shape: experience/education carry company/institution inline
    # (not via profile ID lookup) because this PDF doesn't reference the user's
    # current profile.
    prompt = f"""Du erhältst den Rohtext eines Lebenslaufs (CV) aus einer PDF.
Extrahiere die Inhalte in folgendes JSON-Format. Wenn ein Feld nicht im Text
steht, lass es weg bzw. setze es auf null oder eine leere Liste.

CV-TEXT:
\"\"\"
{text[:14000]}
\"\"\"

Gib NUR ein JSON-Objekt zurück:
{{
  "profile": "2-4 Sätze Profil-Statement (falls nicht vorhanden, freilassen)",
  "experience": [
    {{
      "title":    "Berufsbezeichnung",
      "company":  "Unternehmen",
      "location": "Stadt (falls vorhanden)",
      "start":    "YYYY-MM (falls vorhanden, sonst null)",
      "end":      "YYYY-MM oder 'heute' (falls vorhanden)",
      "bullets":  ["bullet 1", "bullet 2"]
    }}
  ],
  "education": [
    {{
      "degree":      "Abschluss / Studiengang",
      "institution": "Universität / Schule",
      "location":    "Stadt",
      "start":       "YYYY-MM",
      "end":         "YYYY-MM"
    }}
  ],
  "projects": [
    {{
      "title":       "Projekttitel",
      "description": "1-2 Sätze"
    }}
  ],
  "skills": {{
    "Technisch": "kommagetrennte Liste",
    "Methoden":  "kommagetrennte Liste",
    "Sprachen":  "kommagetrennte Liste"
  }}
}}

Regeln:
- Nutze für skills die Kategorien aus dem CV; wenn keine vorhanden, fasse
  alle Hard-Skills unter "Technisch", Soft-Skills unter "Methoden", Sprachen
  unter "Sprachen" zusammen.
- Erfinde keine Inhalte. Wenn der Abschnitt im CV fehlt, gib eine leere Liste
  bzw. ein leeres Objekt zurück.
"""
    try:
        cv_content = _call_gemini_json(prompt, 4096)
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {e}"}), 500

    # Sanity-default missing keys so the frontend can rely on the shape
    cv_content.setdefault("profile", "")
    for key in ("experience", "education", "projects"):
        if not isinstance(cv_content.get(key), list):
            cv_content[key] = []
    if not isinstance(cv_content.get("skills"), dict):
        cv_content["skills"] = {}

    summary = {
        "experience_count": len(cv_content["experience"]),
        "education_count":  len(cv_content["education"]),
        "project_count":    len(cv_content["projects"]),
        "skill_count":      sum(
            len([s for s in str(v).split(",") if s.strip()])
            for v in cv_content["skills"].values()
        ),
    }
    return jsonify({"cv_content": cv_content, "summary": summary})
