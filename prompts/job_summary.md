Analyze the job posting below and return a compact summary.

OUTPUT LANGUAGE: $out_lang. Write ALL content values in $out_lang.

JOB POSTING:
$job_posting

Return a JSON object with exactly this structure:
{
  "company_does": "2-3 sentences: what does the company do? Industry, product, mission.",
  "searching_for": [
    "bullet 1: a concrete requirement for the applicant",
    "bullet 2: ...",
    "bullet 3: ..."
  ],
  "technologies": [
    "technology/tool 1",
    "technology/tool 2"
  ]
}

RULES (this instruction layer is written in English on purpose — it does NOT
change the OUTPUT LANGUAGE defined above; all content values stay $out_lang):
- 4-7 bullets for "searching_for" (responsibilities, skills, experience, soft skills)
- "technologies": ONLY concrete technologies, frameworks, languages, tools — no
  soft skills. Empty list if none are named.
- If the company is not described: best guess based on position/industry;
  if even that is impossible, say so in $out_lang.
- No filler phrases, no repetition.
