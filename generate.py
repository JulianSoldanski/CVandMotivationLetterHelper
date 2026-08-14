"""Prompt builders: profile + posting in, structured content out.
"""
from datetime import date

from cv_layouts import LAYOUTS
from personal_config import get_contact
from gemini import _call_gemini_json
from store import _sort_key, load_profile, load_settings, profile_to_text, projects_to_text




def generate_cv_content(
    job_posting: str, company: str, position: str,
    language: str, custom_notes: str, projects: list
) -> dict:
    out_lang = "German" if language == "de" else "English"
    projects_text = projects_to_text(projects, language)
    notes_block = f"\nAPPLICANT NOTES (must be incorporated):\n{custom_notes}\n" if custom_notes.strip() else ""
    profile = load_profile()
    profile_text = profile_to_text(profile)

    exp = [e for e in profile.get("experience", []) if e.get("visible", True)]
    exp.sort(key=_sort_key, reverse=True)
    
    edu = [e for e in profile.get("education", []) if e.get("visible", True)]
    edu.sort(key=_sort_key, reverse=True)
    visible_projects = [p for p in projects if p.get("visible", True)]

    exp_ids  = [e["id"] for e in exp if e.get("id")]
    edu_ids  = [e["id"] for e in edu if e.get("id")]
    proj_ids = [p["id"] for p in visible_projects if p.get("id")]

    # Skill-category keys are rendered as labels in the CV, so they follow the
    # output language. Everything else in the instruction layer stays English.
    cat_tech = "Tech & Methoden" if language == "de" else "Tech & methods"
    cat_soft = "Soft Skills"
    cat_lang = "Sprachen" if language == "de" else "Languages"
    lang_example = "Deutsch (Muttersprache), Englisch (C1)" if language == "de" else "German (Native), English (C1)"

    applicant = get_contact()["full_name"]
    prompt = f"""You are a professional CV writer. Produce structured CV content for {applicant}.

OUTPUT LANGUAGE: {out_lang}. Write ALL content values in {out_lang}.

APPLICANT PROFILE:
{profile_text}

PROJECTS & ACHIEVEMENTS:
{projects_text}
{notes_block}
JOB POSTING:
{job_posting}

COMPANY: {company or "infer from the job posting"}
POSITION: {position or "infer from the job posting"}

Return a JSON object with exactly this structure:
{{
  "profile": "2-3 sentence profile statement tailored to this position",
  "experience": [
    {{
      "id": "original ID from profile",
      "title": "job title",
      "company": "company name",
      "location": "city, country",
      "bullets": ["bullet 1 tailored to position", "bullet 2"]
    }}
  ],
  "education": [
    {{
      "id": "original ID from profile",
      "degree": "degree name",
      "institution": "school/university name",
      "location": "city, country",
      "details": ["focus / minor / honors"]
    }}
  ],
  "projects": [
    {{
      "id": "project id",
      "title": "project title",
      "description": "project description"
    }}
  ],
  "skills": {{
    "{cat_tech}": "React, TypeScript, Python, ...",
    "{cat_soft}": "...",
    "{cat_lang}": "{lang_example}"
  }}
}}

RULES (this instruction layer is written in English on purpose — it does NOT
change the OUTPUT LANGUAGE defined above; all content values stay {out_lang}):

IDs & coverage:
- Experience: include EVERY entry below, exactly one object per ID, in this
  same order. Do NOT omit, merge, or combine entries — even if two look
  similar or seem less relevant: {exp_ids}
- Education: include EVERY entry below, exactly one object per ID, in this
  same order. Do NOT omit any: {edu_ids}
- Projects: from this list, select ONLY the 3-4 most relevant: {proj_ids}
- Use only the IDs listed above; never invent or alter an ID.

Translation:
- Translate ALL content into {out_lang}: titles, degrees, locations/countries
  (e.g. Deutschland <-> Germany, Norwegen <-> Norway), skill categories,
  project descriptions, education details (focus/minor/honors).
- Do NOT translate proper nouns (company names, university names). Translate a
  legal/company suffix (GmbH/Inc./Ltd.) only when it reads naturally.

Structure & format:
- Return valid JSON only, exactly matching the structure above.
- Keep all structural keys in English as shown. The keys inside "skills" are
  display labels — use them exactly as provided.

Style limits:
- Bullets: concrete activities and results ONLY. Never append "— which
  proves/shows/underlines my XY skills".
- Do not repeat information that already appears elsewhere.
- Do not invent facts.
"""
    return _call_gemini_json(prompt, 4096)


def generate_job_summary(job_posting: str, language: str) -> dict:
    lang = "auf Deutsch" if language == "de" else "in English"
    prompt = f"""Analysiere die folgende Stellenausschreibung und gib eine kompakte Zusammenfassung {lang} zurück.

STELLENAUSSCHREIBUNG:
{job_posting[:8000]}

Gib ein JSON-Objekt zurück mit exakt dieser Struktur:
{{
  "company_does": "2-3 Sätze: Was macht das Unternehmen? Branche, Produkt, Mission.",
  "searching_for": [
    "Stichpunkt 1: konkrete Anforderung an den Bewerber",
    "Stichpunkt 2: ...",
    "Stichpunkt 3: ..."
  ],
  "technologies": [
    "Technologie/Tool 1",
    "Technologie/Tool 2"
  ]
}}

Regeln:
- 4-7 Stichpunkte für "searching_for" (Verantwortlichkeiten, Skills, Erfahrung, Soft Skills)
- "technologies": NUR konkrete Technologien, Frameworks, Sprachen, Tools — keine Soft Skills. Leere Liste falls keine genannt.
- Wenn das Unternehmen nicht beschrieben ist: best-guess auf Basis von Position/Branche, sonst "Nicht in der Ausschreibung beschrieben."
- Keine Floskeln, keine Wiederholungen
"""
    return _call_gemini_json(prompt, 1024)


def generate_anschreiben_content(
    job_posting: str, company: str, position: str,
    contact: str, city: str, language: str,
    custom_notes: str, projects: list,
    company_address: str = ""
) -> dict:
    lang = "auf Deutsch" if language == "de" else "in English"
    today = date.today().strftime("%d. %B %Y") if language == "de" else date.today().strftime("%B %d, %Y")
    projects_text = projects_to_text(projects, language)
    notes_block = f"\nEIGENE HINWEISE (unbedingt einarbeiten):\n{custom_notes}\n" if custom_notes.strip() else ""
    profile_text = profile_to_text(load_profile())

    settings_data  = load_settings()
    style_analysis = (settings_data.get("style_analysis") or "").strip()
    style_example  = (settings_data.get("style_example") or "").strip()
    style_block = ""
    if style_analysis:
        style_block = (
            "\nSTIL-VORGABE DES BEWERBERS (befolge diese Stilrichtlinien strikt — sie destillieren, "
            "wie der Bewerber selbst schreibt):\n"
            f"{style_analysis[:4000]}\n"
        )
    elif style_example:
        style_block = (
            "\nSTIL-BEISPIEL DES BEWERBERS (orientiere dich an Tonfall, Satzlänge, "
            "Wortwahl und Rhythmus — übernimm aber KEINE Inhalte oder konkreten Formulierungen "
            "wörtlich, da es sich um ein anderes Anschreiben handelt):\n"
            f"\"\"\"\n{style_example[:6000]}\n\"\"\"\n"
        )

    applicant = get_contact()["full_name"]
    prompt = f"""Du bist ein professioneller Bewerbungsschreiber. Erstelle strukturierten Inhalt {lang} für das Anschreiben von {applicant}.
{style_block}
PROFIL DES BEWERBERS:
{profile_text}

PROJEKTE & ERFOLGE:
{projects_text}
{notes_block}
STELLENAUSSCHREIBUNG:
{job_posting}

UNTERNEHMEN: {company or "aus Stellenausschreibung entnehmen"}
POSITION: {position or "aus Stellenausschreibung entnehmen"}
ANREDE: {contact}
ORT: {city or "Berlin"}
DATUM: {today}

STIL: Direkt einsteigen, kein "hiermit bewerbe ich mich". Konkrete Beispiele, keine Floskeln. 4-6 kompakte Absätze.

Gib ein JSON-Objekt zurück mit exakt dieser Struktur:
{{
  "company_name": "Firmenname",
  "company_address": "{company_address if company_address else 'Adresse falls bekannt, sonst leer'}",
  "city_date": "{city or 'Berlin'}, {today}",
  "subject": "Bewerbung um die Stelle als [POSITION]",
  "greeting": "{contact},",
  "paragraphs": [
    "Absatz 1 Text...",
    "Absatz 2 Text...",
    "Absatz 3 Text...",
    "Abschluss-Absatz..."
  ]
}}
"""
    return _call_gemini_json(prompt, 3072)
