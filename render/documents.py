"""HTML renderers for CV, Anschreiben and Projektliste.
"""
import re
from html import escape as html_escape

from render.cv_layouts import ANSCHREIBEN_HTML_STYLE, LAYOUTS, PROJECT_LIST_STYLE
from core.personal_config import get_contact, sender_address_html
from core.store import (
    fmt_date, load_profile, normalize_project_detail, project_detail_filled,
    project_locale, _sort_key,
)

def _render_jobs(jobs_content: list, profile: dict, layout: str, language: str = "de") -> str:
    exp_map = {e["id"]: e for e in profile.get("experience", []) if e.get("id")}
    parts = []
    for item in jobs_content:
        entry = exp_map.get(item.get("id"), {})
        if not entry:
            continue
        title    = item.get("title") or entry.get("title", "")
        company  = item.get("company") or entry.get("company", "")
        location = item.get("location") or entry.get("location", "")
        start    = fmt_date(entry.get("start"), language=language)
        end      = fmt_date(entry.get("end"), entry.get("current", False), language=language)
        bullets  = item.get("bullets", entry.get("bullets", []))
        bl_html  = "".join(f"<li>{b}</li>" for b in bullets)

        if layout == "classic":
            parts.append(
                f'<div class="job">'
                f'<div class="job-date">{start}<br>– {end}</div>'
                f'<div class="job-content">'
                f'<div class="job-title">{title}</div>'
                f'<div class="job-company">{company}{(", " + location) if location else ""}</div>'
                f'{"<ul>" + bl_html + "</ul>" if bl_html else ""}'
                f'</div></div>'
            )
        else:
            meta = f"{company}{(', ' + location) if location else ''} · {start} – {end}"
            parts.append(
                f'<div class="job">'
                f'<div class="job-title">{title}</div>'
                f'<div class="job-meta">{meta}</div>'
                f'{"<ul>" + bl_html + "</ul>" if bl_html else ""}'
                f'</div>'
            )
    return "\n".join(parts)


def _render_education(edu_content: list, profile: dict, layout: str, language: str = "de") -> str:
    edu_map = {e["id"]: e for e in profile.get("education", []) if e.get("id")}
    parts = []
    for item in edu_content:
        entry = edu_map.get(item.get("id"), {})
        if not entry:
            continue
        degree      = item.get("degree") or entry.get("degree", "")
        institution = item.get("institution") or entry.get("institution", "")
        location    = item.get("location") or entry.get("location", "")
        start       = fmt_date(entry.get("start"), language=language)
        end         = fmt_date(entry.get("end"), entry.get("current", False), language=language)
        details     = list(item.get("details") or entry.get("details", []))
        det_html = "".join(f"<li>{d}</li>" for d in details)

        if layout == "sidebar":
            parts.append(
                f'<div class="edu-item">'
                f'<div class="edu-title">{degree}</div>'
                f'<div class="edu-meta">{institution}{(", " + location) if location else ""} · {start} – {end}</div>'
                f'</div>'
            )
        elif layout == "classic":
            parts.append(
                f'<div class="job">'
                f'<div class="job-date">{start}<br>– {end}</div>'
                f'<div class="job-content">'
                f'<div class="job-title">{degree}</div>'
                f'<div class="job-company">{institution}{(", " + location) if location else ""}</div>'
                f'{"<ul>" + det_html + "</ul>" if det_html else ""}'
                f'</div></div>'
            )
        else:
            meta_parts = [institution]
            if location:
                meta_parts.append(location)
            meta_parts.append(f"{start} – {end}")
            parts.append(
                f'<div class="job">'
                f'<div class="job-title">{degree}</div>'
                f'<div class="job-meta">{" · ".join(meta_parts)}</div>'
                f'{"<ul>" + det_html + "</ul>" if det_html else ""}'
                f'</div>'
            )
    return "\n".join(parts)


def _render_projects(projects_content: list, all_projects: list, language: str = "de") -> str:
    proj_map = {p["id"]: p for p in all_projects if p.get("id")}
    grade_label = "Grade" if language == "en" else "Note"
    items = []
    for item in projects_content:
        pid   = item if isinstance(item, str) else item.get("id", "")
        p     = proj_map.get(pid)
        if not p:
            continue
        # Fall back to the localized entry, not to the raw source fields — those
        # are in whichever language the project happened to be written in.
        loc   = project_locale(p, language)
        title = (item.get("title") if isinstance(item, dict) else None) or loc["title"] or p["title"]
        desc  = (item.get("description") if isinstance(item, dict) else None) or loc["summary"] or p["description"]
        grade = f" ({grade_label}: {p['grade']})" if p.get("grade") else ""
        link_html = ""
        if p.get("link"):
            # Strip protocol for display ("github.com/..." reads cleaner on a CV
            # than the full https URL), but keep the full URL in href so the
            # link still works when the rendered HTML is exported / printed.
            display = re.sub(r"^https?://", "", p["link"]).rstrip("/")
            link_html = f' (<a href="{p["link"]}" target="_blank" rel="noopener noreferrer">{display}</a>)'
        items.append(f"<li><strong>{title}{grade}</strong>: {desc}{link_html}</li>")
    return "\n".join(items)


def _render_skills_rows(skills: dict) -> str:
    return "\n".join(
        f'<div class="skills-row"><strong>{cat}:</strong><span>{val}</span></div>'
        for cat, val in skills.items()
    )


def _render_skills_dl(skills: dict) -> str:
    return "\n".join(f"<dt>{cat}:</dt><dd>{val}</dd>" for cat, val in skills.items())


def _render_skills_tags(skills: dict) -> str:
    all_s: list[str] = []
    for val in skills.values():
        all_s.extend(s.strip() for s in re.split(r"[,;·•]", val) if s.strip())
    return "".join(f'<span class="skill-tag">{s}</span>' for s in all_s[:12])


I18N = {
    "de": {
        "profile": "Profil", "experience": "Berufserfahrung", "education": "Ausbildung",
        "projects": "Projekte &amp; Erfolge", "skills": "Fähigkeiten &amp; Kenntnisse",
        "skills_classic": "Fähigkeiten", "contact": "Kontakt",
        "core_skills": "Kernkompetenzen", "languages": "Sprachen",
        "lang_de": "Deutsch – Muttersprache", "lang_en": "Englisch – C1",
        "signature": "Mit freundlichen Grüßen",
    },
    "en": {
        "profile": "Profile", "experience": "Work Experience", "education": "Education",
        "projects": "Projects &amp; Achievements", "skills": "Skills &amp; Competencies",
        "skills_classic": "Skills", "contact": "Contact",
        "core_skills": "Core Competencies", "languages": "Languages",
        "lang_de": "German – Native", "lang_en": "English – C1",
        "signature": "Yours sincerely",
    },
}


def render_cv_html(content: dict, layout: str, language: str, all_projects: list) -> str:
    profile   = load_profile()
    ldef      = LAYOUTS.get(layout, LAYOUTS["modern"])
    t         = I18N.get(language, I18N["de"])
    c         = get_contact()
    jobs_html = _render_jobs(content.get("experience", []), profile, layout, language)
    edu_html  = _render_education(content.get("education", []), profile, layout, language)
    proj_html = _render_projects(content.get("projects", []), all_projects, language)
    skills    = content.get("skills", {})
    prof_text = content.get("profile", "")

    if layout == "modern":
        body = f"""<div class="header">
  <h1>{c["full_name"]}</h1>
  <div class="contact">
    <div class="contact-item"><span>📍</span><span>{c["address_dot"]}</span></div>
    <div class="contact-item"><span>📞</span><span>{c["phone"]}</span></div>
    <div class="contact-item"><span>✉️</span><a href="mailto:{c["email"]}">{c["email"]}</a></div>
  </div>
</div>
<div class="section"><h2>{t['profile']}</h2><p>{prof_text}</p></div>
<div class="section"><h2>{t['experience']}</h2>{jobs_html}</div>
<div class="section"><h2>{t['education']}</h2>{edu_html}</div>
<div class="section"><h2>{t['projects']}</h2><ul>{proj_html}</ul></div>
<div class="section"><h2>{t['skills']}</h2>{_render_skills_rows(skills)}</div>"""

    elif layout == "sidebar":
        all_edu = [e for e in profile.get("education", []) if e.get("visible", True)]
        all_edu.sort(key=_sort_key, reverse=True)
        edu_sidebar = _render_education([{"id": e["id"]} for e in all_edu], profile, "sidebar", language)
        body = f"""<div class="page">
  <div class="sidebar">
    <h1>{c["full_name"]}</h1>
    <h2>{t['contact']}</h2>
    <div class="contact-item"><span>📍</span><span>{c["address_sidebar_html"]}</span></div>
    <div class="contact-item"><span>📞</span><span>{c["phone"]}</span></div>
    <div class="contact-item"><span>✉️</span><a href="mailto:{c["email"]}">{c["email"]}</a></div>
    <h2>{t['core_skills']}</h2>
    {_render_skills_tags(skills)}
    <h2>{t['languages']}</h2>
    <p>{t['lang_de']}</p><p>{t['lang_en']}</p>
    <h2>{t['education']}</h2>
    {edu_sidebar}
  </div>
  <div class="main">
    <h2>{t['profile']}</h2>
    <p>{prof_text}</p>
    <h2>{t['experience']}</h2>
    {jobs_html}
    <h2>{t['projects']}</h2>
    <ul>{proj_html}</ul>
  </div>
</div>"""

    else:  # classic
        body = f"""<div class="header">
  <h1>{c["full_name"]}</h1>
  <div class="header-sub">
    <span>{c["address_dot"]}</span>
    <span>{c["phone"]}</span>
    <span><a href="mailto:{c["email"]}">{c["email"]}</a></span>
  </div>
</div>
<h2>{t['profile']}</h2>
<p>{prof_text}</p>
<h2>{t['experience']}</h2>
{jobs_html}
<h2>{t['education']}</h2>
{edu_html}
<h2>{t['projects']}</h2>
<ul>{proj_html}</ul>
<h2>{t['skills_classic']}</h2>
<dl class="skills-block">{_render_skills_dl(skills)}</dl>"""

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{c["full_name"]} - Lebenslauf</title>
{ldef['style']}
</head>
<body>
{body}
</body>
</html>"""


PROJECT_LIST_I18N = {
    "de": {
        "doc_title":  "Projektliste",
        "intro":      "Ausgewählte Projekte im Detail — Ausgangslage, eigener Beitrag, eingesetzte Technologien und Ergebnis.",
        "client":     "Kunde/Arbeitgeber",
        "period":     "Zeitraum",
        "role":       "Rolle",
        "team":       "Team",
        "situation":  "Ausgangslage",
        "contrib":    "Mein Beitrag",
        "tech":       "Technologien",
        "result":     "Ergebnis",
        "summary":    "Kurzbeschreibung",
        "link":       "Link",
        "grade":      "Note",
    },
    "en": {
        "doc_title":  "Project List",
        "intro":      "Selected projects in detail — starting point, my contribution, technologies used and outcome.",
        "client":     "Client/Employer",
        "period":     "Period",
        "role":       "Role",
        "team":       "Team",
        "situation":  "Starting point",
        "contrib":    "My contribution",
        "tech":       "Technologies",
        "result":     "Outcome",
        "summary":    "Summary",
        "link":       "Link",
        "grade":      "Grade",
    },
}


def _pl_link_html(url: str) -> str:
    """Link cell: full URL in href, protocol stripped for display (as on the CV)."""
    display = re.sub(r"^https?://", "", url).rstrip("/")
    return f'<a href="{html_escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{html_escape(display)}</a>'


def _render_project_list_entry(project: dict, index: int, t: dict, language: str) -> str:
    """One project as a clearly delimited block.

    Falls back to the short CV data (description as summary, tags as
    technologies) for projects whose long-form fields aren't filled in yet, so
    the list is usable before every entry has been elaborated.
    """
    detail = normalize_project_detail(project.get("detail"))
    loc    = detail.get(language) or detail["de"]

    title = loc["title"] or project.get("title", "")
    head_right = f'<span class="pl-badge">{t["grade"]} {html_escape(str(project["grade"]))}</span>' if project.get("grade") else ""

    meta_bits = []
    for label, value in (
        (t["client"], detail["client"]),
        (t["period"], detail["period"]),
        (t["role"],   loc["role"]),
        (t["team"],   loc["team_size"] or detail["team_size"]),
    ):
        if value:
            meta_bits.append(f'<span class="pl-meta-item"><strong>{label}:</strong> {html_escape(value)}</span>')
    meta_html = f'<div class="pl-meta">{"".join(meta_bits)}</div>' if meta_bits else ""

    rows = []
    if loc["situation"]:
        rows.append((t["situation"], html_escape(loc["situation"])))
    if loc["contributions"]:
        bullets = "".join(f"<li>{html_escape(c)}</li>" for c in loc["contributions"])
        rows.append((t["contrib"], f"<ul>{bullets}</ul>"))
    if not loc["situation"] and not loc["contributions"]:
        summary = loc["summary"] or project.get("description", "")
        if summary:
            rows.append((t["summary"], html_escape(summary)))

    techs = detail["technologies"] or project.get("tags", [])
    if techs:
        tags_html = "".join(f"<span>{html_escape(tech)}</span>" for tech in techs)
        rows.append((t["tech"], f'<span class="pl-tech">{tags_html}</span>'))
    if loc["result"]:
        rows.append((t["result"], f'<span class="pl-result">{html_escape(loc["result"])}</span>'))
    if project.get("link"):
        rows.append((t["link"], _pl_link_html(project["link"])))

    fields_html = "".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in rows)

    return f"""<div class="pl-project">
  <div class="pl-head">
    <div class="pl-title"><span class="pl-num">{index:02d}</span>{html_escape(title)}</div>
    {head_right}
  </div>
  {meta_html}
  <dl class="pl-fields">{fields_html}</dl>
</div>"""


def select_project_list_entries(all_projects: list, ids: list | None) -> list:
    """Resolve which projects go into the list, preserving the requested order.

    With explicit ids the caller decides (order included); without, everything
    flagged for the list is used, falling back to the CV-visible projects so a
    fresh install still prints something.
    """
    by_id = {p["id"]: p for p in all_projects if p.get("id")}
    if ids:
        return [by_id[pid] for pid in ids if pid in by_id]
    flagged = [p for p in all_projects if normalize_project_detail(p.get("detail"))["in_list"]]
    return flagged or [p for p in all_projects if p.get("visible", True)]


def render_project_list_html(all_projects: list, language: str, layout: str, ids: list | None = None) -> str:
    t = PROJECT_LIST_I18N.get(language, PROJECT_LIST_I18N["de"])
    c = get_contact()
    # Only "modern" and "classic" have a base style that works standalone —
    # "sidebar" is built around a two-column .page shell the list doesn't use.
    layout   = layout if layout in ("modern", "classic") else "modern"
    base     = LAYOUTS[layout]["style"]
    entries  = select_project_list_entries(all_projects, ids)
    body     = "\n".join(
        _render_project_list_entry(p, i, t, language) for i, p in enumerate(entries, start=1)
    )

    header = f"""<div class="header">
  <h1>{c["full_name"]}</h1>
  <div class="pl-doc-title">{t["doc_title"]}</div>
  <p class="pl-intro">{t["intro"]}</p>
  <div class="contact">
    <div class="contact-item"><span>📍</span><span>{c["address_dot"]}</span></div>
    <div class="contact-item"><span>📞</span><span>{c["phone"]}</span></div>
    <div class="contact-item"><span>✉️</span><a href="mailto:{c["email"]}">{c["email"]}</a></div>
  </div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{c["full_name"]} - {t["doc_title"]}</title>
{base}
{PROJECT_LIST_STYLE}
</head>
<body class="pl-{layout}">
{header}
{body}
</body>
</html>"""


def render_anschreiben_html(content: dict, language: str) -> str:
    company_name    = content.get("company_name", "")
    company_address = content.get("company_address", "")
    city_date       = content.get("city_date", "")
    subject         = content.get("subject", "")
    greeting        = content.get("greeting", "Sehr geehrte Damen und Herren,")
    paragraphs      = content.get("paragraphs", [])
    signer          = get_contact()["full_name"]

    company_block = f"<strong>{company_name}</strong>"
    if company_address:
        company_block += "<br/>" + company_address.replace("\n", "<br/>")

    paras_html = "\n".join(f"<p>{p}</p>" for p in paragraphs)

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{signer} - Anschreiben</title>
{ANSCHREIBEN_HTML_STYLE}
</head>
<body>
<div class="content-box">
  <div class="address-row">
    <div class="recipient-address">{company_block}</div>
    <div class="sender-address">{sender_address_html()}</div>
  </div>
  <p class="date-line">{city_date}</p>
</div>
<div class="content-box">
  <p class="subject-line">{subject}</p>
  <p><strong>{greeting}</strong></p>
  {paras_html}
  <p class="signature">{I18N.get(language, I18N["de"])["signature"]}<br>{signer}</p>
</div>
</body>
</html>"""
