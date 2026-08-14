// Profile: experience, education, skills, languages.

// ── Profile entries (experience / education) ──
function renderEntries(section) {
  const list = document.getElementById(section + 'List');
  const entries = [...(profile[section] || [])];
  const key = (e) => e.current ? '9999-99' : (e.end || e.start || '0000-00');
  entries.sort((a, b) => key(b).localeCompare(key(a)));

  list.innerHTML = '';
  if (!entries.length) {
    list.innerHTML = '<p style="font-size:0.78rem;color:#ccc;margin-bottom:0.4rem">Keine Einträge.</p>';
    return;
  }

  entries.forEach(e => {
    const title = section === 'experience'
      ? (e.title || 'Ohne Titel')
      : (e.degree || 'Ohne Bezeichnung');
    const metaMain = section === 'experience'
      ? (e.company || '')
      : (e.institution || '');
    const period = `${e.start || '–'} – ${e.current ? 'heute' : (e.end || '–')}`;

    const d = document.createElement('div');
    d.className = 'entry-item' + (e.visible === false ? ' hidden-entry' : '');
    d.innerHTML = `
      <div class="entry-row">
        <div class="entry-main">
          <div class="entry-title" title="${esc(title)}">${esc(title)}</div>
          <div class="entry-meta">${esc(metaMain)} · ${esc(period)}</div>
        </div>
        <div class="entry-actions">
          <button class="proj-btn" title="${e.visible === false ? 'Einblenden' : 'Ausblenden'}" onclick="toggleEntryVisible('${section}','${e.id}')">${e.visible === false ? '🙈' : '👁'}</button>
          <button class="proj-btn" onclick="openEntryModal('${section}','${e.id}')">✏️</button>
          <button class="proj-btn danger" onclick="deleteEntry('${section}','${e.id}')">🗑</button>
        </div>
      </div>`;
    list.appendChild(d);
  });
}

function addBulletRow(text = '') {
  const list = document.getElementById('bulletsList');
  const row = document.createElement('div');
  row.className = 'bullet-row';
  row.innerHTML = `
    <textarea rows="2" placeholder="Punkt beschreiben...">${esc(text)}</textarea>
    <button type="button" class="bullet-remove" onclick="this.parentElement.remove()">✕</button>
  `;
  list.appendChild(row);
}

function clearEntryForm() {
  document.getElementById('entryId').value = '';
  document.getElementById('entryTitle').value = '';
  document.getElementById('entryCompany').value = '';
  document.getElementById('entryLocation').value = '';
  document.getElementById('entryDegree').value = '';
  document.getElementById('entryInstitution').value = '';
  document.getElementById('entryEduLocation').value = '';
  document.getElementById('entryStart').value = '';
  document.getElementById('entryEnd').value = '';
  document.getElementById('entryCurrent').checked = false;
  document.getElementById('entryVisible').value = 'true';
  document.getElementById('bulletsList').innerHTML = '';
  addBulletRow('');
  toggleCurrentCheck();
}

function openEntryModal(section, id = null) {
  document.getElementById('entrySection').value = section;
  clearEntryForm();
  const isExperience = section === 'experience';

  document.getElementById('expFields').style.display = isExperience ? 'block' : 'none';
  document.getElementById('eduFields').style.display = isExperience ? 'none' : 'block';
  document.getElementById('entryModalTitle').textContent = id
    ? (isExperience ? 'Stelle bearbeiten' : 'Ausbildung bearbeiten')
    : (isExperience ? 'Stelle hinzufügen' : 'Ausbildung hinzufügen');
  document.getElementById('bulletsLabel').textContent = isExperience ? 'Bullet Points' : 'Details';

  if (id) {
    const entry = (profile[section] || []).find(x => x.id === id);
    if (!entry) return;

    document.getElementById('entryId').value = id;
    document.getElementById('entryStart').value = entry.start || '';
    document.getElementById('entryEnd').value = entry.end || '';
    document.getElementById('entryCurrent').checked = !!entry.current;
    document.getElementById('entryVisible').value = (entry.visible === false) ? 'false' : 'true';

    if (isExperience) {
      document.getElementById('entryTitle').value = entry.title || '';
      document.getElementById('entryCompany').value = entry.company || '';
      document.getElementById('entryLocation').value = entry.location || '';
    } else {
      document.getElementById('entryDegree').value = entry.degree || '';
      document.getElementById('entryInstitution').value = entry.institution || '';
      document.getElementById('entryEduLocation').value = entry.location || '';
    }

    const list = document.getElementById('bulletsList');
    list.innerHTML = '';
    const points = isExperience ? (entry.bullets || []) : (entry.details || []);
    if (points.length) points.forEach(p => addBulletRow(p));
    else addBulletRow('');
    toggleCurrentCheck();
  }

  document.getElementById('entryModalOverlay').classList.add('open');
}

function closeEntryModal() {
  document.getElementById('entryModalOverlay').classList.remove('open');
}

function closeEntryModalOnBackdrop(e) {
  if (e.target === document.getElementById('entryModalOverlay')) closeEntryModal();
}

function toggleCurrentCheck() {
  const current = document.getElementById('entryCurrent').checked;
  const endInput = document.getElementById('entryEnd');
  endInput.disabled = current;
  if (current) endInput.value = '';
}

async function saveEntry() {
  const section = document.getElementById('entrySection').value;
  const id = document.getElementById('entryId').value;
  const isExperience = section === 'experience';

  const start = document.getElementById('entryStart').value || null;
  const current = document.getElementById('entryCurrent').checked;
  const end = current ? null : (document.getElementById('entryEnd').value || null);
  const visible = document.getElementById('entryVisible').value === 'true';
  const points = [...document.querySelectorAll('#bulletsList textarea')]
    .map(x => x.value.trim())
    .filter(Boolean);

  let payload;
  if (isExperience) {
    const title = document.getElementById('entryTitle').value.trim();
    const company = document.getElementById('entryCompany').value.trim();
    const location = document.getElementById('entryLocation').value.trim();
    if (!title || !company) {
      alert('Berufsbezeichnung und Unternehmen sind Pflicht.');
      return;
    }
    payload = { title, company, location, start, end, current, bullets: points, visible };
  } else {
    const degree = document.getElementById('entryDegree').value.trim();
    const institution = document.getElementById('entryInstitution').value.trim();
    const location = document.getElementById('entryEduLocation').value.trim();
    if (!degree || !institution) {
      alert('Abschluss und Institution sind Pflicht.');
      return;
    }
    payload = { degree, institution, location, start, end, current, details: points, visible };
  }

  try {
    if (id) {
      const res = await fetch(`/profile/${section}/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const updated = await res.json();
      if (updated.error) {
        alert(updated.error);
        return;
      }
      const idx = (profile[section] || []).findIndex(x => x.id === id);
      if (idx !== -1) profile[section][idx] = updated;
    } else {
      const res = await fetch(`/profile/${section}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const created = await res.json();
      if (created.error) {
        alert(created.error);
        return;
      }
      profile[section] = [...(profile[section] || []), created];
    }
    renderEntries(section);
    closeEntryModal();
  } catch (e) {
    alert('Fehler beim Speichern: ' + e.message);
  }
}

async function toggleEntryVisible(section, id) {
  const entry = (profile[section] || []).find(x => x.id === id);
  if (!entry) return;
  const payload = {...entry, visible: entry.visible === false ? true : false};
  const res = await fetch(`/profile/${section}/${id}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  const updated = await res.json();
  if (updated.error) return alert(updated.error);
  const idx = profile[section].findIndex(x => x.id === id);
  if (idx !== -1) profile[section][idx] = updated;
  renderEntries(section);
}

async function deleteEntry(section, id) {
  if (!confirm('Eintrag löschen?')) return;
  const res = await fetch(`/profile/${section}/${id}`, { method: 'DELETE' });
  const data = await res.json();
  if (data.error) return alert(data.error);
  profile[section] = (profile[section] || []).filter(x => x.id !== id);
  renderEntries(section);
}

function renderSkillList(containerId, items, formatter) {
  const box = document.getElementById(containerId);
  box.innerHTML = '';
  if (!items || !items.length) {
    box.innerHTML = '<span style="font-size:0.72rem;color:#bbb">Noch nichts hinzugefügt.</span>';
    return;
  }
  items.forEach(item => {
    const tag = document.createElement('span');
    tag.className = 'skill-tag-item';
    const text = document.createElement('span');
    text.textContent = formatter(item);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.title = 'Löschen';
    btn.textContent = '✕';
    btn.onclick = () => deleteSkillItem(containerId, item.id);
    tag.appendChild(text);
    tag.appendChild(btn);
    box.appendChild(tag);
  });
}

function renderSkills() {
  renderSkillList('hardSkillsList', profile.hard_skills || [], x => x.name || '');
  renderSkillList('softSkillsList', profile.soft_skills || [], x => x.name || '');
  renderSkillList('languagesList', profile.languages || [], x => x.level ? `${x.name} (${x.level})` : x.name);
}

async function addSkill(listName) {
  const inputId = listName === 'hard_skills' ? 'hardSkillInput' : 'softSkillInput';
  const input = document.getElementById(inputId);
  const name = (input.value || '').trim();
  if (!name) return;

  const res = await fetch(`/profile/list/${listName}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name })
  });
  const item = await res.json();
  if (item.error) return alert(item.error);

  profile[listName] = [...(profile[listName] || []), item];
  input.value = '';
  renderSkills();
}

async function addLanguage() {
  const nameInput = document.getElementById('languageInput');
  const levelInput = document.getElementById('languageLevelInput');
  const name = (nameInput.value || '').trim();
  const level = (levelInput.value || '').trim();
  if (!name) return;

  const res = await fetch('/profile/list/languages', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name, level })
  });
  const item = await res.json();
  if (item.error) return alert(item.error);

  profile.languages = [...(profile.languages || []), item];
  nameInput.value = '';
  levelInput.value = '';
  renderSkills();
}

async function deleteSkillItem(containerId, itemId) {
  let listName = 'hard_skills';
  if (containerId === 'softSkillsList') listName = 'soft_skills';
  if (containerId === 'languagesList') listName = 'languages';

  const res = await fetch(`/profile/list/${listName}/${itemId}`, { method: 'DELETE' });
  const data = await res.json();
  if (data.error) return alert(data.error);

  profile[listName] = (profile[listName] || []).filter(x => x.id !== itemId);
  renderSkills();
}

document.getElementById('job_posting').addEventListener('keydown', e => {
  if(e.ctrlKey && e.key==='Enter') generate();
});
