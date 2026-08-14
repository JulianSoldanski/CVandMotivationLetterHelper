You are given the raw text of a CV extracted from a PDF. Extract its contents
into the JSON format below. If a field does not appear in the text, leave it
out, or set it to null / an empty list.

CV TEXT:
"""
$text
"""

Return ONLY a JSON object:
{
  "profile": "2-4 sentence profile statement (leave empty if the CV has none)",
  "experience": [
    {
      "title":    "job title",
      "company":  "company",
      "location": "city (if present)",
      "start":    "YYYY-MM (if present, otherwise null)",
      "end":      "YYYY-MM, or 'heute' for a current position (if present)",
      "bullets":  ["bullet 1", "bullet 2"]
    }
  ],
  "education": [
    {
      "degree":      "degree / field of study",
      "institution": "university / school",
      "location":    "city",
      "start":       "YYYY-MM",
      "end":         "YYYY-MM"
    }
  ],
  "projects": [
    {
      "title":       "project title",
      "description": "1-2 sentences"
    }
  ],
  "skills": {
    "Technisch": "comma-separated list",
    "Methoden":  "comma-separated list",
    "Sprachen":  "comma-separated list"
  }
}

RULES (this instruction layer is written in English on purpose — it does NOT
change the language of the extracted content):
- This is extraction, not translation: keep every value in the language the CV
  itself uses. Do not translate titles, degrees, bullets or locations.
- For "skills", use the categories from the CV. If it has none, group all hard
  skills under "Technisch", soft skills under "Methoden" and languages under
  "Sprachen" — these three keys stay exactly as spelled here, they are the
  labels shown in the CV.
- Use the literal string 'heute' for an ongoing position, whatever the language.
- Do not invent content. If a section is missing from the CV, return an empty
  list or an empty object.
