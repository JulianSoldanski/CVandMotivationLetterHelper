// init() - loads every dataset once and wires up global listeners.

async function init() {
  // Demo badge is fire-and-forget; failure (e.g. /mode missing on an older
  // backend) shouldn't block the rest of the init flow.
  fetch('/mode').then(r => r.json()).then(m => {
    if (m && m.demo) document.getElementById('demoBadge').style.display = '';
  }).catch(() => {});

  const [projectsRes, profileRes, layoutsRes, appsRes, settingsRes, queueRes] = await Promise.all([
    fetch('/projects'),
    fetch('/profile'),
    fetch('/layouts'),
    fetch('/applications'),
    fetch('/settings'),
    fetch('/queue')
  ]);
  projects = await projectsRes.json();
  profile = await profileRes.json();
  const layouts = await layoutsRes.json();
  layouts.forEach(l => { layoutStyles[l.id] = l.style; });
  applications = await appsRes.json();
  const settings = await settingsRes.json();
  document.getElementById('styleExample').value  = settings.style_example || '';
  document.getElementById('styleAnalysis').value = settings.style_analysis || '';
  updateStyleCount();
  renderProjects();
  renderEntries('experience');
  renderEntries('education');
  renderSkills();
  updateAppsCount();
  queue = await queueRes.json();
  updateQueueBadge();

  // Enter im Queue-URL-Feld → hinzufügen
  const qUrl  = document.getElementById('queueAddUrl');
  const qNote = document.getElementById('queueAddNote');
  if (qUrl)  qUrl.addEventListener('keydown',  e => { if (e.key === 'Enter') addQueueFromInput(); });
  if (qNote) qNote.addEventListener('keydown', e => { if (e.key === 'Enter') addQueueFromInput(); });

  // Gen-Timer: start/extend a segment whenever the user identifies a posting
  // (typing, paste, programmatic fill via Auto-Ausfüllen, or queue prefill).
  ['company', 'position'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', ensureGenTimerStarted);
  });
  ensureGenTimerStarted();
}
