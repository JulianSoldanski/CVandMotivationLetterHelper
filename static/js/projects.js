// Projects and the long-form Projektliste.

// ── Projects ──
function renderProjects() {
  const list = document.getElementById('projectsList');
  list.innerHTML = '';
  if (!projects.length) {
    list.innerHTML = '<p style="font-size:0.78rem;color:#ccc;margin-bottom:0.4rem">Keine Projekte.</p>';
    return;
  }
  projects.forEach(p => {
    const d = document.createElement('div');
    d.className = 'project-item' + (p.visible ? '' : ' hidden-proj');
    const linkBtn = p.link
      ? `<a class="proj-btn" href="${esc(p.link)}" target="_blank" rel="noopener noreferrer" title="${esc(p.link)}">🔗</a>`
      : '';
    const plFlag = hasPlDetail(p)
      ? `<span class="pl-flag" title="${p.detail && p.detail.in_list === false ? 'Details erfasst – nicht in der Projektliste' : 'Details für die Projektliste erfasst'}">${p.detail && p.detail.in_list === false ? '📄✕' : '📄'}</span>`
      : '';
    d.innerHTML = `
      <div class="proj-row">
        <div class="proj-main">
          <div class="proj-title" title="${esc(p.title)}">${esc(p.title)}${plFlag}</div>
          <div class="proj-meta">${(p.tags||[]).join(' · ')}${p.grade ? ' · Note '+p.grade : ''}</div>
        </div>
        <div class="proj-actions">
          ${linkBtn}
          <button class="proj-btn" title="${p.visible?'Ausblenden':'Einblenden'}" onclick="toggleVisible('${p.id}')">${p.visible?'👁':'🙈'}</button>
          <button class="proj-btn" onclick="openEditModal('${p.id}')">✏️</button>
          <button class="proj-btn danger" onclick="deleteProject('${p.id}')">🗑</button>
        </div>
      </div>`;
    list.appendChild(d);
  });
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

async function toggleVisible(id) {
  const p = projects.find(x=>x.id===id); if(!p) return;
  await fetch(`/projects/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,visible:!p.visible})});
  p.visible=!p.visible; renderProjects();
}

async function deleteProject(id) {
  if(!confirm('Projekt löschen?')) return;
  await fetch(`/projects/${id}`,{method:'DELETE'});
  projects=projects.filter(p=>p.id!==id); renderProjects();
}

function openAddModal() {
  editingId=null;
  document.getElementById('modalTitle').textContent='Projekt hinzufügen';
  document.getElementById('modalProjectId').value='';
  document.getElementById('modalProjTitle').value='';
  document.getElementById('modalProjDesc').value='';
  document.getElementById('modalProjTags').value='';
  document.getElementById('modalProjGrade').value='';
  document.getElementById('modalProjLink').value='';
  fillPlDetail(emptyPlDetail());
  document.getElementById('plDetailBody').classList.remove('open');
  document.getElementById('plDetailChevron').classList.remove('open');
  document.getElementById('modalOverlay').classList.add('open');
}

function openEditModal(id) {
  const p=projects.find(x=>x.id===id); if(!p) return;
  editingId=id;
  document.getElementById('modalTitle').textContent='Projekt bearbeiten';
  document.getElementById('modalProjectId').value=id;
  document.getElementById('modalProjTitle').value=p.title;
  document.getElementById('modalProjDesc').value=p.description;
  document.getElementById('modalProjTags').value=(p.tags||[]).join(', ');
  document.getElementById('modalProjGrade').value=p.grade||'';
  document.getElementById('modalProjLink').value=p.link||'';
  fillPlDetail(p.detail);
  // Open the detail block right away when there's something to see.
  const filled = hasPlDetail(p);
  document.getElementById('plDetailBody').classList.toggle('open', filled);
  document.getElementById('plDetailChevron').classList.toggle('open', filled);
  document.getElementById('modalOverlay').classList.add('open');
}

function closeModal() { document.getElementById('modalOverlay').classList.remove('open'); }
function closeModalOnBackdrop(e) { if(e.target===document.getElementById('modalOverlay')) closeModal(); }

async function saveProject() {
  const title=document.getElementById('modalProjTitle').value.trim();
  const desc =document.getElementById('modalProjDesc').value.trim();
  if(!title||!desc){alert('Titel und Beschreibung sind Pflicht.');return;}
  const tags =document.getElementById('modalProjTags').value.split(',').map(t=>t.trim()).filter(Boolean);
  const grade=document.getElementById('modalProjGrade').value.trim()||null;
  const link =document.getElementById('modalProjLink').value.trim()||null;
  const detail=readPlDetail();
  if(editingId){
    const res=await fetch(`/projects/${editingId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,description:desc,tags,grade,link,detail})});
    const u=await res.json();
    const idx=projects.findIndex(p=>p.id===editingId); if(idx!==-1) projects[idx]=u;
  } else {
    const res=await fetch('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,description:desc,tags,grade,link,detail,visible:true})});
    projects.push(await res.json());
  }
  renderProjects(); closeModal();
}

// ── Projektliste: detail fields in the project modal ──
const PL_LANGS = ['de','en'];

// Fields the form shows per language. `team_size`, `auto` and `src` also live
// in the block but are maintained by the backend translation — the form must
// carry them through untouched, hence plDetailLoaded below.
const PL_TEXT_FIELDS = ['title','summary','role','situation','result'];

function emptyPlDetail() {
  const d = { client:'', period:'', team_size:'', technologies:[], in_list:true };
  PL_LANGS.forEach(l => {
    d[l] = { title:'', summary:'', role:'', situation:'', contributions:[], result:'',
             team_size:'', auto:[], src:'' };
  });
  return d;
}

// Last detail loaded into the form, so saving can tell which fields the user
// actually changed (those stop counting as machine-translated) and can keep
// the ones the form doesn't render.
let plDetailLoaded = emptyPlDetail();

function hasPlDetail(p) {
  const d = p.detail; if (!d) return false;
  if (d.client || d.period || d.team_size || (d.technologies||[]).length) return true;
  return PL_LANGS.some(l => {
    const b = d[l] || {};
    return b.role || b.situation || b.result || (b.contributions||[]).length;
  });
}

function togglePlDetail() {
  document.getElementById('plDetailBody').classList.toggle('open');
  document.getElementById('plDetailChevron').classList.toggle('open');
}

function switchPlLang(lang) {
  PL_LANGS.forEach(l => {
    const up = l.charAt(0).toUpperCase() + l.slice(1);
    document.getElementById('plTab'+up).classList.toggle('active', l === lang);
    document.getElementById('plPane'+up).classList.toggle('active', l === lang);
  });
}

function fillPlDetail(detail) {
  const d = Object.assign(emptyPlDetail(), detail || {});
  PL_LANGS.forEach(l => { d[l] = Object.assign(emptyPlDetail()[l], d[l] || {}); });
  plDetailLoaded = JSON.parse(JSON.stringify(d));
  document.getElementById('plClient').value   = d.client || '';
  document.getElementById('plPeriod').value   = d.period || '';
  document.getElementById('plTeamSize').value = d.team_size || '';
  document.getElementById('plTech').value     = (d.technologies||[]).join(', ');
  document.getElementById('plInList').checked = d.in_list !== false;
  PL_LANGS.forEach(l => {
    const b = d[l];
    PL_TEXT_FIELDS.forEach(f => { document.getElementById(plFieldId(f, l)).value = b[f] || ''; });
    document.getElementById('plContrib_'+l).value = (b.contributions||[]).join('\n');
  });
  switchPlLang('de');
}

function plFieldId(field, lang) {
  return 'pl' + field.charAt(0).toUpperCase() + field.slice(1) + '_' + lang;
}

function readPlDetail() {
  const detail = {
    client:       document.getElementById('plClient').value.trim(),
    period:       document.getElementById('plPeriod').value.trim(),
    team_size:    document.getElementById('plTeamSize').value.trim(),
    technologies: document.getElementById('plTech').value.split(',').map(t=>t.trim()).filter(Boolean),
    in_list:      document.getElementById('plInList').checked,
  };
  PL_LANGS.forEach(l => {
    const prev  = plDetailLoaded[l] || {};
    // Start from what was loaded so team_size/src survive the round-trip.
    const block = Object.assign({}, prev);
    PL_TEXT_FIELDS.forEach(f => { block[f] = document.getElementById(plFieldId(f, l)).value.trim(); });
    block.contributions = document.getElementById('plContrib_'+l).value.split('\n').map(s=>s.trim()).filter(Boolean);
    // A field the user edited by hand is no longer machine output, so the
    // auto-translation must never overwrite it again.
    block.auto = (prev.auto || []).filter(f => {
      const before = prev[f], now = block[f];
      return Array.isArray(before) ? before.join('\n') === (now||[]).join('\n') : (before || '') === (now || '');
    });
    detail[l] = block;
  });
  return detail;
}

async function draftProjectDetail() {
  const title = document.getElementById('modalProjTitle').value.trim();
  const desc  = document.getElementById('modalProjDesc').value.trim();
  if (!title || !desc) { alert('Titel und Beschreibung zuerst ausfüllen.'); return; }
  const btn = document.getElementById('plDraftBtn');
  btn.disabled = true; const label = btn.textContent; btn.textContent = 'Entwerfe…';
  try {
    const res = await fetch('/project-list/draft', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        id: editingId, title, description: desc,
        tags: document.getElementById('modalProjTags').value.split(',').map(t=>t.trim()).filter(Boolean),
        grade: document.getElementById('modalProjGrade').value.trim() || null,
        detail: readPlDetail(),
      })
    });
    const data = await res.json();
    if (data.error) { alert('Fehler: ' + data.error); return; }
    fillPlDetail(data.detail);
  } catch(e) {
    alert('Verbindungsfehler: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = label;
  }
}

// ── Projektliste: preview & export ──
let projectListHtml = '';

function openProjectListModal() {
  if (!projects.length) { alert('Noch keine Projekte angelegt.'); return; }
  const picker = document.getElementById('plistPicker');
  picker.innerHTML = '';
  projects.forEach(p => {
    const checked = p.detail && p.detail.in_list === false ? '' : 'checked';
    const row = document.createElement('label');
    row.className = 'plist-pick';
    row.innerHTML = `<input type="checkbox" value="${esc(p.id)}" ${checked} onchange="renderProjectList()"/>
      <span class="plist-pick-title">${esc(p.title)}${hasPlDetail(p) ? ' <span class="pl-flag">📄</span>' : ''}</span>`;
    picker.appendChild(row);
  });
  document.getElementById('plistLang').value = currentLanguage || 'de';
  document.getElementById('plistOverlay').classList.add('open');
  renderProjectList();
}

function closePlistModal() { document.getElementById('plistOverlay').classList.remove('open'); }
function closePlistOnBackdrop(e) { if(e.target===document.getElementById('plistOverlay')) closePlistModal(); }

function plistSelectedIds() {
  return [...document.querySelectorAll('#plistPicker input:checked')].map(cb => cb.value);
}

function setAllPlistPicks(on) {
  document.querySelectorAll('#plistPicker input').forEach(cb => { cb.checked = on; });
  renderProjectList();
}

async function renderProjectList() {
  const ids   = plistSelectedIds();
  const frame = document.getElementById('plistFrame');
  if (!ids.length) {
    projectListHtml = '';
    frame.srcdoc = '<div style="font-family:sans-serif;color:#bbb;text-align:center;padding:3rem 1rem;font-size:0.85rem">Kein Projekt ausgewählt.</div>';
    return;
  }
  try {
    const res = await fetch('/project-list/render', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        ids,
        language: document.getElementById('plistLang').value,
        layout:   document.getElementById('plistLayout').value,
      })
    });
    const data = await res.json();
    if (data.error) { alert('Render-Fehler: ' + data.error); return; }
    projectListHtml = data.html;
    frame.srcdoc = data.html;
  } catch(e) {
    alert('Verbindungsfehler: ' + e.message);
  }
}

function projectListFilename(ext) {
  const lang  = document.getElementById('plistLang').value;
  const today = new Date().toISOString().slice(0, 10);
  const name  = (lang === 'en' ? 'Project_List' : 'Projektliste');
  return `${name}_${today}.${ext}`;
}

async function exportProjectList() {
  if (!projectListHtml) { alert('Zuerst Projekte auswählen.'); return; }
  const filename = projectListFilename('html');
  try {
    await fetch('/save', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ doc_type:'projektliste', filename, html: projectListHtml })
    });
  } catch(e) { console.warn('Speichern fehlgeschlagen:', e.message); }

  const titled = projectListHtml.replace(/<title>[^<]*<\/title>/i, `<title>${filename.replace('.html','')}</title>`);
  const win = window.open('', '_blank');
  win.document.write(titled);
  win.document.close();
  win.addEventListener('load', () => { win.print(); });
}

function openPlistInNewTab() {
  if (!projectListHtml) { alert('Zuerst Projekte auswählen.'); return; }
  const blob = new Blob([projectListHtml], {type:'text/html'});
  window.open(URL.createObjectURL(blob), '_blank');
}
