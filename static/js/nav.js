// Top-level view switching (Generator / Queue / Profil / Bewerbungen / Statistik).

// ── View switching (Generator ↔ Queue ↔ Profil ↔ Bewerbungen ↔ Statistik) ──
// Style-Einstellungen sind seit dem Merge eine Sektion innerhalb des Profil-Tabs.
let activeView = 'generator';

function showView(view) {
  activeView = view;
  document.getElementById('generatorView').style.display    = view === 'generator'    ? 'grid'  : 'none';
  document.getElementById('queueView').style.display        = view === 'queue'        ? 'block' : 'none';
  document.getElementById('profileView').style.display      = view === 'profile'      ? 'block' : 'none';
  document.getElementById('applicationsView').style.display = view === 'applications' ? 'block' : 'none';
  document.getElementById('statsView').style.display        = view === 'stats'        ? 'block' : 'none';
  document.getElementById('navGenerator').classList.toggle('active',    view === 'generator');
  document.getElementById('navQueue').classList.toggle('active',        view === 'queue');
  document.getElementById('navProfile').classList.toggle('active',      view === 'profile');
  document.getElementById('navApplications').classList.toggle('active', view === 'applications');
  document.getElementById('navStats').classList.toggle('active',        view === 'stats');
  if (view === 'applications') renderApplications();
  if (view === 'queue') refreshQueue();
  if (view === 'profile') refreshProfileView();
  if (view === 'stats') { rejFilterStage = null; renderStats(); }
  if (view === 'generator') ensureGenTimerStarted();
}

function refreshProfileView() {
  renderProjects();
  renderEntries('experience');
  renderEntries('education');
  renderSkills();
}
