You are preparing a project list (reference list) for applications to
consultancies. Turn the short entry below into structured project details — in
German AND in English.

PROJECT TITLE: $title
DESCRIPTION: $description
TAGS: $tags
GRADE: $grade
ALREADY RECORDED (if filled, carry it over instead of inventing something new):
$existing

Answer with JSON only, in exactly this structure:
{
  "client": "client/employer/university, otherwise \"\"",
  "period": "e.g. 03/2024 – 07/2024, otherwise \"\"",
  "team_size": "e.g. 4 Personen, otherwise \"\"",
  "technologies": ["concrete technologies, methods, tools"],
  "de": {
    "title": "factual project title (what it was, not the internal name)",
    "summary": "the short description, used in the CV",
    "role": "e.g. Fullstack-Entwickler, Requirements Engineer",
    "situation": "ONE sentence on the initial problem",
    "contributions": ["2-3 bullets in active voice, each starting with a verb"],
    "result": "ONE sentence: what changed measurably or visibly",
    "team_size": "team size, e.g. \"4 Personen\", otherwise \"\""
  },
  "en": { "title": "...", "summary": "...", "role": "...", "situation": "...", "contributions": ["..."], "result": "...", "team_size": "e.g. \"4 people\"" }
}

RULES (this instruction layer is written in English on purpose — it does NOT
change the output language of the two blocks):
- EVERY text field must be written in the language of its block: the "de" block
  entirely in German, the "en" block entirely in English — even when the title
  or description above is written in the other language.
- The English version is a translation of the same statements, not a new one.
- Do NOT invent facts. If client, period or team size do not follow from the
  text: empty string.
- Derive "result" only from what is evidenced (e.g. a grade, a hackathon win, a
  shipped prototype) — no invented percentages.
- Keep bullets short (max ~15 words), active, without "I" / "Ich".
