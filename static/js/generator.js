// Document generator: research timer, input modes, generate,
// editors, preview and export.

// ── Gen-Timer (per-application "Zeit investiert" tracker) ──
// Simple wall-clock: a segment runs from when (company,position) is loaded
// in the Generator until the next Generieren click. On each click the
// elapsed seconds are sent to /generate and a fresh segment starts. No
// pause on tab blur / view switch — per user spec. Persisted in
// localStorage so a page refresh doesn't lose the segment start.
const GEN_TIMER_LS_KEY = 'cvc.genTimer';

function getGenTimerKey() {
  const c = (document.getElementById('company')  || {}).value || '';
  const p = (document.getElementById('position') || {}).value || '';
  const key = c.trim() + '|' + p.trim();
  return key === '|' ? '' : key;
}

function readGenTimer() {
  try {
    const raw = localStorage.getItem(GEN_TIMER_LS_KEY);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    if (!obj || typeof obj.key !== 'string' || typeof obj.startedAt !== 'number') return null;
    return obj;
  } catch { return null; }
}

function writeGenTimer(key, startedAt) {
  try {
    if (!key) localStorage.removeItem(GEN_TIMER_LS_KEY);
    else      localStorage.setItem(GEN_TIMER_LS_KEY, JSON.stringify({ key, startedAt }));
  } catch {}
}

// Start a segment if none is running for the current (company,position),
// or if the stored segment belongs to a different posting.
function ensureGenTimerStarted() {
  const key = getGenTimerKey();
  if (!key) return;
  const cur = readGenTimer();
  if (!cur || cur.key !== key) writeGenTimer(key, Date.now());
}

// Return elapsed seconds for the current key and immediately restart the
// segment so the next iteration begins counting. Returns 0 when no matching
// segment exists (e.g. user pasted fields and clicked Generieren instantly).
function consumeGenTimerElapsed() {
  const key = getGenTimerKey();
  if (!key) return 0;
  const cur = readGenTimer();
  const now = Date.now();
  writeGenTimer(key, now);  // start the next segment right away
  if (!cur || cur.key !== key) return 0;
  return Math.max(0, Math.round((now - cur.startedAt) / 1000));
}


// ── Input mode ──
function switchInputMode(mode, btn) {
  inputMode = mode;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('textMode').style.display = mode === 'text' ? 'block' : 'none';
  document.getElementById('urlMode').style.display  = mode === 'url'  ? 'block' : 'none';
}

async function fetchJobUrl() {
  const url = document.getElementById('job_url').value.trim();
  if (!url) return;
  const btn = document.getElementById('fetchBtn');
  btn.disabled = true; btn.textContent = '…';
  try {
    const res  = await fetch('/fetch-job', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url})
    });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    document.getElementById('job_posting_url').value = data.text;
    document.getElementById('job_posting_url').style.color = '#2c3e50';
    document.getElementById('job_posting_url').removeAttribute('readonly');
    autoFillFields();
  } catch(e) {
    alert('Fehler: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Laden';
  }
}

async function autoFillFields() {
  const text = getJobPosting();
  if (!text) return;
  const btn = document.getElementById('autoFillBtn');
  btn.disabled = true; btn.textContent = '…';
  try {
    const res  = await fetch('/extract-fields', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({job_posting: text})
    });
    const data = await res.json();
    if (data.error) { console.warn(data.error); return; }
    if (data.company)         setIfEmpty('company',         data.company);
    if (data.position)        setIfEmpty('position',        data.position);
    if (data.contact)         setIfEmpty('contact',         data.contact);
    if (data.city)            setIfEmpty('city',            data.city);
    if (data.company_address) setIfEmpty('company_address', data.company_address);
    // Programmatic .value assignment doesn't fire 'input' — kick the timer
    // here so an auto-filled posting starts a segment.
    ensureGenTimerStarted();
  } catch(e) {
    console.warn('Auto-Ausfüllen fehlgeschlagen:', e.message);
  } finally {
    btn.disabled = false; btn.textContent = '✨ Auto-Ausfüllen';
  }
}

function setIfEmpty(id, value) {
  const el = document.getElementById(id);
  if (el && !el.value.trim()) el.value = value;
}

function getJobPosting() {
  if (inputMode === 'url') {
    return document.getElementById('job_posting_url').value.trim();
  }
  return document.getElementById('job_posting').value.trim();
}

// ── Layout ──
function selectLayout(el) {
  document.querySelectorAll('.layout-card').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  layout = el.dataset.layout;
  applyLayoutToCurrentCv(layout);
}

function setLayoutCard(layoutId) {
  document.querySelectorAll('.layout-card').forEach(c => c.classList.remove('active'));
  const selected = document.querySelector(`.layout-card[data-layout="${layoutId}"]`);
  if (selected) selected.classList.add('active');
}

// ── Doc type ──
function selectDocType(el) {
  document.querySelectorAll('.doc-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  docType = el.dataset.value;
}

// ── Collapsibles ──
function toggleSection(id) {
  const body    = document.getElementById('body-' + id);
  const chevron = document.getElementById('chevron-' + id);
  body.classList.toggle('open');
  chevron.classList.toggle('open');
}

// ── Tab ──
function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  document.getElementById('content-' + tab).classList.add('active');
  const showActions = tab === 'cv' || tab === 'anschreiben';
  document.getElementById('docActions').style.display = showActions ? 'flex' : 'none';
}

// ── Generate ──
function setLoading(on) {
  const btn = document.getElementById('generateBtn');
  document.getElementById('btnText').style.display = on ? 'none' : 'inline';
  document.getElementById('spinner').style.display  = on ? 'block' : 'none';
  btn.disabled = on;
}
function showError(msg) {
  const el = document.getElementById('errorMsg');
  el.textContent = msg; el.style.display = msg ? 'block' : 'none';
}
function renderJobOverview(summary, sourceText) {
  const does  = summary.company_does || '';
  const wants = Array.isArray(summary.searching_for) ? summary.searching_for : [];
  const techs = Array.isArray(summary.technologies)  ? summary.technologies  : [];

  document.getElementById('stelleDoes').textContent = does || '–';
  document.getElementById('stelleWants').innerHTML = wants.length
    ? wants.map(w => `<li>${esc(w)}</li>`).join('')
    : '<li style="color:#999;font-style:italic;list-style:none;margin-left:-0.95rem">Keine Angaben extrahiert.</li>';
  document.getElementById('stelleTech').innerHTML = techs.length
    ? techs.map(t => `<span class="stelle-tech-tag">${esc(t)}</span>`).join('')
    : '<span class="stelle-tech-empty">Keine Technologien in der Ausschreibung genannt.</span>';
  document.getElementById('stelleSource').textContent = sourceText || '';

  document.getElementById('jobOverview').style.display = 'block';
}

function setDoc(type, html) {
  generatedDocs[type] = html;
  const iframe = document.getElementById('iframe-' + type);
  const empty  = document.getElementById('empty-' + type);
  iframe.srcdoc = html; iframe.style.display = 'block'; empty.style.display = 'none';
  document.getElementById('badge-' + type).textContent = '✓';
  document.getElementById('tab-' + type).classList.add('ready');
}

async function generate() {
  const jobPosting = getJobPosting();
  if (!jobPosting) { showError('Bitte Stellenausschreibung einfügen oder URL laden.'); return; }
  showError(''); setLoading(true);
  currentLanguage = document.getElementById('language').value;
  const payload = {
    job_posting:  jobPosting,
    job_url:      document.getElementById('job_url').value.trim(),
    company:      document.getElementById('company').value,
    position:     document.getElementById('position').value,
    contact:      document.getElementById('contact').value || 'Sehr geehrte Damen und Herren',
    city:         document.getElementById('city').value || 'Soest',
    language:     currentLanguage,
    doc_type:     docType,
    custom_notes:    document.getElementById('custom_notes').value,
    company_address: document.getElementById('company_address').value,
    layout,
    tracked_seconds: consumeGenTimerElapsed(),
  };
  try {
    const res  = await fetch('/generate', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.error) { showError(data.error); return; }
    if (data.layout_used) layout = data.layout_used;

    if (data.cv_content)          { generatedContent.cv = data.cv_content; buildCvEditor(data.cv_content); }
    if (data.anschreiben_content) { generatedContent.anschreiben = data.anschreiben_content; buildAnschreibenEditor(data.anschreiben_content); }
    if (data.job_summary)         { renderJobOverview(data.job_summary, data.job_posting || jobPosting); }
    if (data.application) {
      const i = applications.findIndex(a => a.id === data.application.id);
      if (i >= 0) applications[i] = data.application;
      else        applications.push(data.application);
      updateAppsCount();
    }

    // Falls die generierte Stelle aus der Queue stammte: Queue-Eintrag auf
    // 'done' setzen und mit der frisch erzeugten Bewerbung verknüpfen.
    const usedUrl = (payload.job_url || '').trim();
    if (usedUrl) {
      const match = queue.find(q => q.status === 'pending' && q.url === usedUrl);
      if (match) {
        markQueueDoneSilently(match.id, data.application && data.application.id);
      }
    }

    // Show editor tab
    document.getElementById('empty-edit').style.display = 'none';
    document.getElementById('editorWrap').style.display = 'flex';
    document.getElementById('cvEditor').style.display = data.cv_content ? 'block' : 'none';
    document.getElementById('anschreibenEditor').style.display = data.anschreiben_content ? 'block' : 'none';
    document.getElementById('badge-edit').textContent = '✓';
    document.getElementById('tab-edit').classList.add('ready');
    switchTab('edit');
  } catch(e) {
    showError('Verbindungsfehler: ' + e.message);
  } finally {
    setLoading(false);
  }
}

// ── Editor builders ──
function buildCvEditor(content) {
  document.getElementById('edProfile').value = content.profile || '';

  // Experience
  const expList = document.getElementById('edExpList');
  expList.innerHTML = '';
  (content.experience || []).forEach((item, i) => {
    const entry = (profile.experience || []).find(e => e.id === item.id) || {};
    const title = (item.title || entry.title || item.id) + (entry.company ? ` @ ${entry.company}` : '');
    const div = document.createElement('div');
    div.className = 'editor-job';
    div.innerHTML = `<div class="editor-job-header">${esc(title)}</div>`;
    (item.bullets || []).forEach((b, bi) => {
      const row = document.createElement('div');
      row.className = 'editor-bullet';
      row.innerHTML = `<textarea rows="2" data-exp="${i}" data-bi="${bi}">${esc(b)}</textarea>
        <button type="button" class="bullet-remove" title="Entfernen" onclick="this.closest('.editor-bullet').remove()">✕</button>`;
      div.appendChild(row);
    });
    expList.appendChild(div);
  });

  // Education – just show IDs as read-only info, no editable bullets needed
  const eduList = document.getElementById('edEduList');
  eduList.innerHTML = '';
  (content.education || []).forEach(item => {
    const entry = (profile.education || []).find(e => e.id === item.id) || {};
    const title = entry.degree ? `${entry.degree} – ${entry.institution || ''}` : item.id;
    const div = document.createElement('div');
    div.style.cssText = 'font-size:0.82rem;color:#555;padding:0.25rem 0;border-bottom:1px solid #f0f0f0;';
    div.textContent = title;
    eduList.appendChild(div);
  });

  // Projects
  buildProjectEditor(content.projects || []);

  // Skills
  const skillsList = document.getElementById('edSkillsList');
  skillsList.innerHTML = '';
  Object.entries(content.skills || {}).forEach(([cat, val]) => {
    const row = document.createElement('div');
    row.className = 'editor-skill-row';
    row.innerHTML = `<input type="text" value="${esc(cat)}" data-skill-cat placeholder="Kategorie"/>
                     <input type="text" value="${esc(val)}" data-skill-val placeholder="Skills…"/>`;
    skillsList.appendChild(row);
  });
}

function buildProjectEditor(selectedItems) {
  const list = document.getElementById('edProjectsList');
  list.innerHTML = '';
  selectedItems.forEach(item => {
    const id = typeof item === 'string' ? item : item.id;
    addProjectRow(id, typeof item === 'object' ? item : null);
  });
  rebuildProjectDropdown();
}

function addProjectRow(id, contentItem = null) {
  const p = projects.find(x => x.id === id);
  if (!p) return;
  const list = document.getElementById('edProjectsList');
  const displayTitle = (contentItem && contentItem.title) ? contentItem.title : p.title;
  const row = document.createElement('div');
  row.className = 'editor-bullet';
  row.dataset.projectId = id;
  if (contentItem) row.dataset.projectContent = JSON.stringify(contentItem);
  row.draggable = true;
  row.innerHTML = `<span class="drag-handle" title="Verschieben">⠿</span>
    <span style="flex:1;font-size:0.82rem;color:#2c3e50;padding:0.35rem 0.1rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(displayTitle)}">${esc(displayTitle)}</span>
    <button type="button" class="bullet-remove" title="Entfernen" onclick="removeProjectRow(this,'${id}')">✕</button>`;
  row.addEventListener('dragstart', onProjDragStart);
  row.addEventListener('dragover',  onProjDragOver);
  row.addEventListener('dragleave', onProjDragLeave);
  row.addEventListener('drop',      onProjDrop);
  row.addEventListener('dragend',   onProjDragEnd);
  list.appendChild(row);
  rebuildProjectDropdown();
}

function removeProjectRow(btn, id) {
  btn.closest('.editor-bullet').remove();
  rebuildProjectDropdown();
}

function rebuildProjectDropdown() {
  const sel = document.getElementById('edProjectsAdd');
  const selected = new Set([...document.querySelectorAll('#edProjectsList [data-project-id]')].map(r => r.dataset.projectId));
  sel.innerHTML = '<option value="">+ Projekt hinzufügen…</option>';
  projects.filter(p => p.visible && !selected.has(p.id)).forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.title.length > 60 ? p.title.slice(0, 58) + '…' : p.title;
    sel.appendChild(opt);
  });
}

function addProjectToEditor(sel) {
  const id = sel.value;
  if (!id) return;
  addProjectRow(id);
  sel.value = '';
}

let dragSrc = null;
function onProjDragStart(e) {
  dragSrc = this;
  e.dataTransfer.effectAllowed = 'move';
  this.style.opacity = '0.4';
}
function onProjDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  this.classList.add('drag-over');
}
function onProjDragLeave() { this.classList.remove('drag-over'); }
function onProjDrop(e) {
  e.preventDefault();
  this.classList.remove('drag-over');
  if (dragSrc && dragSrc !== this) {
    const list = document.getElementById('edProjectsList');
    const kids = [...list.children];
    const srcIdx  = kids.indexOf(dragSrc);
    const destIdx = kids.indexOf(this);
    if (srcIdx < destIdx) list.insertBefore(dragSrc, this.nextSibling);
    else                  list.insertBefore(dragSrc, this);
  }
}
function onProjDragEnd() {
  this.style.opacity = '';
  document.querySelectorAll('#edProjectsList .drag-over').forEach(el => el.classList.remove('drag-over'));
  dragSrc = null;
}

function readProjectIds() {
  return [...document.querySelectorAll('#edProjectsList [data-project-id]')].map(r => {
    if (r.dataset.projectContent) {
      try { return JSON.parse(r.dataset.projectContent); } catch(e) {}
    }
    return r.dataset.projectId;
  });
}

function buildAnschreibenEditor(content) {
  document.getElementById('edSubject').value = content.subject || '';
  const paraList = document.getElementById('edParaList');
  paraList.innerHTML = '';
  (content.paragraphs || []).forEach((p, i) => {
    paraList.appendChild(makeParaBlock(p, i));
  });
}

function makeParaBlock(text, idx) {
  const div = document.createElement('div');
  div.className = 'editor-para';
  div.style.marginBottom = '0.7rem';
  div.innerHTML = `
    <div class="editor-bullet">
      <textarea rows="4" data-para="${idx}">${esc(text)}</textarea>
      <button type="button" class="bullet-remove" title="Entfernen" onclick="this.closest('.editor-para').remove()">✕</button>
    </div>
    <div class="ai-improve-row">
      <input type="text" class="ai-improve-input" placeholder="KI-Anweisung: z.B. Kürzer fassen, React betonen…"
        onkeydown="if(event.key==='Enter'){event.preventDefault();improveParaWithAI(this);}"/>
      <button type="button" class="ai-improve-btn" onclick="improveParaWithAI(this.previousElementSibling)">
        <span>✨ KI</span>
        <div class="ai-improve-spinner"></div>
      </button>
    </div>`;
  return div;
}

async function improveParaWithAI(inputEl) {
  const paraDiv = inputEl.closest('.editor-para');
  const ta = paraDiv.querySelector('textarea');
  const instruction = inputEl.value.trim();
  if (!instruction) { inputEl.focus(); return; }
  const text = ta.value.trim();
  if (!text) return;

  const btn = inputEl.nextElementSibling;
  btn.disabled = true;
  btn.querySelector('span').style.display = 'none';
  btn.querySelector('.ai-improve-spinner').style.display = 'block';

  try {
    const res = await fetch('/improve-text', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ text, instruction })
    });
    const data = await res.json();
    if (data.error) { alert('Fehler: ' + data.error); return; }
    ta.value = data.text;
    inputEl.value = '';
    ta.style.background = '#f0faf4';
    setTimeout(() => { ta.style.background = ''; }, 1200);
  } catch(e) {
    alert('Verbindungsfehler: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.querySelector('span').style.display = '';
    btn.querySelector('.ai-improve-spinner').style.display = 'none';
  }
}

// ── Read editor back into content dict ──
function readCvContent() {
  const content = JSON.parse(JSON.stringify(generatedContent.cv || {}));
  content.profile = document.getElementById('edProfile').value;

  // bullets — re-collect per job from remaining DOM rows
  document.querySelectorAll('#edExpList .editor-job').forEach((jobDiv, expIdx) => {
    if (content.experience && content.experience[expIdx]) {
      content.experience[expIdx].bullets = [...jobDiv.querySelectorAll('textarea')]
        .map(ta => ta.value)
        .filter(v => v.trim());
    }
  });

  // skills
  const skillsEl = document.querySelectorAll('#edSkillsList .editor-skill-row');
  const skills = {};
  skillsEl.forEach(row => {
    const cat = row.querySelector('[data-skill-cat]').value.trim();
    const val = row.querySelector('[data-skill-val]').value.trim();
    if (cat) skills[cat] = val;
  });
  content.skills = skills;
  content.projects = readProjectIds();
  return content;
}

function readAnschreibenContent() {
  const content = JSON.parse(JSON.stringify(generatedContent.anschreiben || {}));
  content.subject = document.getElementById('edSubject').value;
  content.paragraphs = [...document.querySelectorAll('#edParaList textarea')]
    .map(ta => ta.value)
    .filter(v => v.trim());
  return content;
}

// ── Render preview ──
async function renderPreview(type) {
  const btn = document.getElementById(type === 'cv' ? 'renderCvBtn' : 'renderAnBtn');
  btn.disabled = true;
  btn.querySelector('span').textContent = 'Wird gerendert…';
  try {
    const payload = {
      doc_type: type,
      language: currentLanguage,
      content:  type === 'cv' ? readCvContent() : readAnschreibenContent(),
      layout,
    };
    const res  = await fetch('/render', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.error) { alert('Render-Fehler: ' + data.error); return; }
    setDoc(type, data.html);
    switchTab(type);
  } catch(e) {
    alert('Verbindungsfehler: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.querySelector('span').textContent = 'Vorschau erstellen →';
  }
}

function applyLayoutToCurrentCv(layoutId) {
  // With new two-step approach, re-render if we have content
  if (generatedContent.cv) {
    layout = layoutId;
    renderPreview('cv');
  }
}

// ── Actions ──
async function copyHtml() {
  const html = generatedDocs[activeTab];
  if (!html) { alert('Zuerst Dokument generieren.'); return; }
  await navigator.clipboard.writeText(html);
  const btn = document.getElementById('copyHtmlBtn');
  btn.textContent = '✓ Kopiert!'; btn.classList.add('copied');
  setTimeout(() => { btn.textContent = 'HTML kopieren'; btn.classList.remove('copied'); }, 2000);
}

function buildPdfFilename(docType) {
  const company  = (document.getElementById('company').value  || '').trim();
  const position = (document.getElementById('position').value || '').trim();
  const today    = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const type     = docType === 'anschreiben' ? 'Anschreiben' : 'CV';
  const parts    = [type, company, position, today].filter(Boolean);
  return parts.join('_').replace(/\s+/g, '_').replace(/[^A-Za-z0-9_\-äöüÄÖÜß]/g, '') + '.pdf';
}

async function exportPdf() {
  const html = generatedDocs[activeTab];
  if (!html) { alert('Zuerst Dokument generieren.'); return; }
  const filename = buildPdfFilename(activeTab);
  const htmlFilename = filename.replace('.pdf', '.html');

  // Save to server folder silently
  try {
    await fetch('/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ doc_type: activeTab, filename: htmlFilename, html })
    });
  } catch(e) { console.warn('Speichern fehlgeschlagen:', e.message); }

  // Open print dialog for PDF export
  const titled = html.replace(/<title>[^<]*<\/title>/i, `<title>${filename.replace('.pdf','')}</title>`);
  const win = window.open('', '_blank');
  win.document.write(titled);
  win.document.close();
  win.addEventListener('load', () => { win.print(); });
}

function openInNewTab() {
  const html = generatedDocs[activeTab];
  if (!html) { alert('Zuerst Dokument generieren.'); return; }
  const blob = new Blob([html], {type:'text/html'});
  window.open(URL.createObjectURL(blob), '_blank');
}
