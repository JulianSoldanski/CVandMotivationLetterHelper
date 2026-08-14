"""Prompt builders: profile + posting in, structured content out.

The prompt texts themselves live in prompts/*.md — this module only collects
the values they interpolate.
"""
from datetime import date

import prompts
from render.cv_layouts import LAYOUTS
from core.personal_config import get_contact
from ai.gemini import _call_gemini_json
from core.store import _sort_key, load_profile, load_settings, profile_to_text, projects_to_text




def generate_cv_content(
    job_posting: str, company: str, position: str,
    language: str, custom_notes: str, projects: list
) -> dict:
    out_lang = "German" if language == "de" else "English"
    projects_text = projects_to_text(projects, language)
    notes_block = (
        prompts.render("notes_block", custom_notes=custom_notes)
        if custom_notes.strip() else ""
    )
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

    prompt = prompts.render(
        "cv_content",
        applicant=get_contact()["full_name"],
        out_lang=out_lang,
        profile_text=profile_text,
        projects_text=projects_text,
        notes_block=notes_block,
        job_posting=job_posting,
        company=company or "infer from the job posting",
        position=position or "infer from the job posting",
        cat_tech=cat_tech,
        cat_soft=cat_soft,
        cat_lang=cat_lang,
        lang_example=lang_example,
        exp_ids=exp_ids,
        edu_ids=edu_ids,
        proj_ids=proj_ids,
    )
    return _call_gemini_json(prompt, 4096)


def generate_job_summary(job_posting: str, language: str) -> dict:
    prompt = prompts.render(
        "job_summary",
        out_lang="German" if language == "de" else "English",
        job_posting=job_posting[:8000],
    )
    return _call_gemini_json(prompt, 1024)


def generate_anschreiben_content(
    job_posting: str, company: str, position: str,
    contact: str, city: str, language: str,
    custom_notes: str, projects: list,
    company_address: str = ""
) -> dict:
    today = date.today().strftime("%d. %B %Y") if language == "de" else date.today().strftime("%B %d, %Y")
    notes_block = (
        prompts.render("notes_block", custom_notes=custom_notes)
        if custom_notes.strip() else ""
    )

    settings_data  = load_settings()
    style_analysis = (settings_data.get("style_analysis") or "").strip()
    style_example  = (settings_data.get("style_example") or "").strip()
    style_block = ""
    if style_analysis:
        style_block = prompts.render(
            "anschreiben_style_analysis", style_analysis=style_analysis[:4000]
        )
    elif style_example:
        style_block = prompts.render(
            "anschreiben_style_example", style_example=style_example[:6000]
        )

    prompt = prompts.render(
        "anschreiben",
        out_lang="German" if language == "de" else "English",
        applicant=get_contact()["full_name"],
        style_block=style_block,
        profile_text=profile_to_text(load_profile()),
        projects_text=projects_to_text(projects, language),
        notes_block=notes_block,
        job_posting=job_posting,
        company=company or "infer from the job posting",
        position=position or "infer from the job posting",
        contact=contact,
        city=city or "Berlin",
        today=today,
        company_address=company_address or "postal address if known, otherwise empty",
    )
    return _call_gemini_json(prompt, 3072)
