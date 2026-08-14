Extract the following information from this job posting. Return null for any
information that is not present.

JOB POSTING:
$job_posting

Return a JSON object:
{
  "company": "company name, or null",
  "position": "exact job title, or null",
  "contact": "German salutation — personal if a name is known, e.g. 'Sehr geehrte Frau Müller', otherwise exactly 'Sehr geehrte Damen und Herren'",
  "city": "city of the company location, or null",
  "company_address": "full postal address with street, ZIP and city — only if explicitly named in the posting, otherwise null"
}

Values are copied straight into the letter: keep company, position, city and
address exactly as the posting spells them, and never translate them.
