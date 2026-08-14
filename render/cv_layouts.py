# CV / cover letter CSS (no personal data). Layout "structure" lives in render_cv_html.

LAYOUTS = {
    "modern": {
        "name": "Modern",
        "style": """<style>
  body { font-family: "Inter","Lato",sans-serif; margin:10px auto; max-width:800px; padding:10px; color:#2c3e50; line-height:1.35; background:#f8f9fa; font-size:10px; }
  h1 { font-size:2em; font-weight:700; margin:0; color:#000; }
  h2 { color:#2c3e50; font-size:1.1em; margin-top:0; margin-bottom:0.4em; border-bottom:1px solid #4B5D67; padding-bottom:0.2em; font-weight:700; }
  p,li { font-size:0.9em; margin:0.3em 0; }
  ul { padding-left:16px; margin:0.4em 0; }
  .header { margin-bottom:0.8em; padding:1.5em; border:1px solid #e0e0e0; border-radius:8px; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.05); }
  .header h1 { border-bottom:3px solid #4B5D67; padding-bottom:0.5em; margin-bottom:0.8em; }
  .contact { font-size:0.95em; color:#666; display:flex; flex-wrap:wrap; gap:1.5em; align-items:center; }
  .contact-item { display:flex; align-items:center; gap:0.4em; }
  .section { margin-bottom:0.8em; padding:1em; border:1px solid #e0e0e0; border-radius:8px; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.05); }
  .job { margin-bottom:0.8em; }
  .job-title { font-weight:600; color:#2c3e50; font-size:1em; }
  .job-meta { font-style:italic; color:#6c757d; font-size:0.85em; margin-bottom:0.3em; }
  .skills-row { margin:0.55em 0; }
  .skills-row strong {
    color:#2c3e50;
    font-size:0.88em;
    display:block;
    width:auto;
    margin-bottom:0.18em;
  }
  .skills-row span {
    font-size:0.86em;
    color:#495057;
    display:block;
    width:auto;
    line-height:1.45;
    word-break:break-word;
  }
  a { color:#3498db; text-decoration:none; }
  @media print { body { background:#fff !important; } }
</style>""",
    },
    "sidebar": {
        "name": "Sidebar",
        "style": """<style>
  * { box-sizing:border-box; }
  body { font-family:"Inter","Lato",sans-serif; margin:0; padding:10px; color:#2c3e50; line-height:1.4; background:#f8f9fa; font-size:10px; }
  h1 { font-size:1.9em; font-weight:700; margin:0 0 0.2em 0; color:#fff; }
  h2 { font-size:1em; font-weight:700; margin:0 0 0.5em 0; text-transform:uppercase; letter-spacing:0.06em; }
  p,li { font-size:0.88em; margin:0.25em 0; }
  ul { padding-left:14px; margin:0.3em 0; }
  .page { display:flex; min-height:100vh; max-width:800px; margin:0 auto; background:#fff; box-shadow:0 2px 8px rgba(0,0,0,.08); }
  .sidebar { width:260px; flex-shrink:0; background:#4B5D67; color:#fff; padding:1.5em 1.2em; }
  .sidebar h2 { color:#c8d8e0; border-bottom:1px solid rgba(255,255,255,.2); padding-bottom:0.3em; margin-top:1.2em; }
  .sidebar h2:first-of-type { margin-top:1em; }
  .sidebar p, .sidebar li { color:#dde8ee; font-size:0.85em; }
  .sidebar a { color:#a8cfe0; }
  .sidebar .contact-item { display:flex; gap:0.4em; align-items:flex-start; margin-bottom:0.35em; font-size:0.85em; color:#dde8ee; }
  .sidebar .skill-tag { display:inline-block; background:rgba(255,255,255,.12); border-radius:3px; padding:0.15em 0.5em; margin:0.15em 0.15em 0.15em 0; font-size:0.8em; color:#e8f0f4; }
  .sidebar .edu-item { margin-bottom:0.8em; }
  .sidebar .edu-title { font-weight:600; color:#fff; font-size:0.88em; }
  .sidebar .edu-meta { font-size:0.78em; color:#b0c8d4; }
  .main { flex:1; padding:1.5em 1.4em; }
  .main h2 { color:#4B5D67; border-bottom:2px solid #4B5D67; padding-bottom:0.25em; margin-top:1.2em; margin-bottom:0.6em; }
  .main h2:first-of-type { margin-top:0; }
  .job { margin-bottom:0.9em; }
  .job-title { font-weight:700; color:#2c3e50; font-size:0.95em; }
  .job-meta { color:#7f8c8d; font-size:0.8em; font-style:italic; margin-bottom:0.2em; }
  a { color:#3498db; text-decoration:none; }
  @media print { body { background:#fff !important; } .page { box-shadow:none; } }
</style>""",
    },
    "classic": {
        "name": "Klassisch",
        "style": """<style>
  body { font-family:Georgia,"Times New Roman",serif; margin:10px auto; max-width:780px; padding:20px; color:#1a1a1a; line-height:1.5; background:#fff; font-size:11px; }
  h1 { font-size:2em; font-weight:700; margin:0 0 0.15em 0; color:#000; letter-spacing:0.02em; }
  h2 { font-size:0.95em; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:#000; margin:1.2em 0 0.4em 0; border-bottom:1px solid #000; padding-bottom:0.2em; }
  p,li { font-size:0.92em; margin:0.3em 0; }
  ul { padding-left:18px; margin:0.3em 0; }
  .header { border-bottom:2px solid #000; padding-bottom:0.8em; margin-bottom:1em; }
  .header-sub { font-size:0.88em; color:#555; margin-top:0.4em; display:flex; flex-wrap:wrap; gap:1.2em; }
  .job { margin-bottom:0.9em; display:grid; grid-template-columns:140px 1fr; gap:0 1em; }
  .job-date { font-size:0.82em; color:#555; padding-top:0.15em; }
  .job-content .job-title { font-weight:700; color:#000; }
  .job-content .job-company { font-size:0.85em; color:#444; font-style:italic; margin-bottom:0.2em; }
  .skills-block { display:grid; grid-template-columns:160px 1fr; gap:0.4em 0.8em; align-items:baseline; }
  .skills-block dt { font-weight:700; font-size:0.88em; color:#000; }
  .skills-block dd { font-size:0.88em; color:#333; margin:0; }
  a { color:#000; text-decoration:underline; }
  @media print { body { background:#fff !important; padding:0; } }
</style>""",
    },
}

# Extra CSS for the project list ("Projektliste"). Appended AFTER a layout's
# base style so it inherits the CV's fonts/colors and reads as the same family
# of documents. Only `.pl-*` classes are defined here — the base style keeps
# ownership of body/h1/h2/a. `body.pl-classic` variants drop the card look so
# the serif layout stays flat like its CV counterpart.
PROJECT_LIST_STYLE = """<style>
  .pl-doc-title { font-size:1.15em; font-weight:700; color:#4B5D67; margin:0.6em 0 0.2em 0; }
  .pl-intro { font-size:0.9em; color:#555; margin:0.2em 0 0 0; }
  .pl-project { margin-bottom:0.7em; padding:0.9em 1.1em; border:1px solid #e0e0e0; border-radius:8px; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.05); page-break-inside:avoid; break-inside:avoid; }
  .pl-head { display:flex; justify-content:space-between; align-items:baseline; gap:1em; border-bottom:1px solid #ececec; padding-bottom:0.35em; margin-bottom:0.45em; }
  .pl-title { font-size:1.05em; font-weight:700; color:#2c3e50; }
  .pl-num { color:#8a9aa4; font-weight:700; margin-right:0.4em; }
  .pl-badge { font-size:0.78em; font-weight:600; color:#41535d; background:#eef2f4; border-radius:10px; padding:0.12em 0.6em; white-space:nowrap; }
  .pl-meta { display:flex; flex-wrap:wrap; gap:0.2em 1.1em; font-size:0.82em; color:#6c757d; margin-bottom:0.5em; }
  .pl-meta-item strong { color:#4B5D67; font-weight:600; }
  .pl-fields { display:grid; grid-template-columns:112px 1fr; gap:0.32em 0.9em; margin:0; }
  .pl-fields dt { font-size:0.82em; font-weight:700; color:#4B5D67; }
  .pl-fields dd { margin:0; font-size:0.88em; color:#333; line-height:1.45; }
  .pl-fields dd ul { margin:0; padding-left:15px; }
  .pl-fields dd li { font-size:1em; margin:0.1em 0; }
  .pl-tech span { display:inline-block; background:#eef2f4; border-radius:3px; padding:0.1em 0.45em; margin:0 0.25em 0.2em 0; font-size:0.95em; color:#41535d; }
  .pl-result { font-weight:600; color:#2c3e50; }

  body.pl-classic .pl-project { border:none; border-radius:0; box-shadow:none; background:transparent; padding:0; margin-bottom:1.1em; border-bottom:1px solid #ddd; padding-bottom:0.8em; }
  body.pl-classic .pl-project:last-of-type { border-bottom:none; }
  body.pl-classic .pl-head { border-bottom:none; padding-bottom:0.1em; }
  body.pl-classic .pl-title { color:#000; }
  body.pl-classic .pl-fields dt,
  body.pl-classic .pl-meta-item strong { color:#000; }
  body.pl-classic .pl-badge,
  body.pl-classic .pl-tech span { background:transparent; border:1px solid #bbb; border-radius:2px; color:#333; }
  body.pl-classic .pl-doc-title { color:#000; }
  /* The classic base styles .header-sub, not .contact — restore the row here. */
  body.pl-classic .contact { display:flex; flex-wrap:wrap; gap:0.4em 1.2em; font-size:0.88em; color:#555; margin-top:0.5em; }
  body.pl-classic .contact-item { display:flex; align-items:center; gap:0.4em; }

  @media print { .pl-project { page-break-inside:avoid; break-inside:avoid; } }
</style>"""

ANSCHREIBEN_HTML_STYLE = """<style>
  body { font-family:"Inter","Lato",sans-serif; margin:10px auto; max-width:800px; padding:10px; color:#2c3e50; line-height:1.5; background:#f8f9fa; font-size:11px; }
  .header { margin-bottom:0.8em; padding:1.5em; border:1px solid #e0e0e0; border-radius:8px; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.05); }
  h1 { font-size:2em; font-weight:700; margin:0; color:#000; border-bottom:3px solid #4B5D67; padding-bottom:0.5em; margin-bottom:0.8em; }
  .contact { font-size:0.95em; color:#666; display:flex; flex-wrap:wrap; gap:1.5em; align-items:center; }
  .contact-item { display:flex; align-items:center; gap:0.4em; }
  .content-box { margin-bottom:0.8em; padding:1.5em; border:1px solid #e0e0e0; border-radius:8px; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.05); }
  .address-row { display:flex; justify-content:space-between; margin-bottom:2em; }
  .recipient-address { font-size:0.9em; color:#555; line-height:1.6; }
  .sender-address { font-size:0.9em; color:#555; text-align:right; line-height:1.6; }
  .date-line { text-align:right; margin-bottom:2em; font-size:0.9em; color:#666; }
  .subject-line { font-weight:700; font-size:1em; margin-bottom:1.5em; color:#000; }
  p { margin-bottom:1.2em; font-size:0.95em; line-height:1.6; }
  p:last-child { margin-bottom:0; }
  ul { padding-left:20px; margin:0.5em 0 1.2em 0; }
  li { font-size:0.9em; margin-bottom:0.4em; line-height:1.5; }
  .signature { margin-top:2em; font-weight:600; }
  strong { color:#000; }
  @media print { body { background:#fff !important; } }
</style>"""
