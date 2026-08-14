// Shared mutable state and the application-stage constants.
//
// Loaded first: every other file reads these globals.

let activeTab    = 'edit';
let docType      = 'both';
let layout       = 'modern';
let inputMode    = 'text';
let generatedDocs    = {};
let generatedContent = {};  // raw content dicts from /generate
let currentLanguage  = 'de';
let layoutStyles = {};
let projects = [];
let profile = { experience: [], education: [], hard_skills: [], soft_skills: [], languages: [] };
let editingId = null;
let applications = [];
// Aktive Ausgangsstufe im Absagen-Panel; null = alle zeigen.
let rejFilterStage = null;

const APP_STAGES = [
  { key: 'documents_created', label: 'Erstellt' },
  { key: 'application_sent',  label: 'Versendet' },
  { key: 'interview_1',       label: '1. Gespräch' },
  { key: 'interview_2',       label: '2. Gespräch' },
  { key: 'interview_3',       label: '3. Gespräch' },
  { key: 'rejected',          label: 'Abgesagt' },
];
const LINEAR_STAGES = APP_STAGES.filter(s => s.key !== 'rejected');

// Display-only: 'documents_created' und 'application_sent' sind fachlich
// dieselbe Stufe und werden in Funnel/Donut als eine Zeile gezeigt. Das
// Datenmodell, das Stage-Dropdown und die Historie bleiben getrennt.
const MERGED_SENT_KEY = 'application_sent';
const MERGED_SENT_LABEL = 'Erstellt & versendet';
const MERGED_AWAY_KEY = 'documents_created';
const FUNNEL_STAGES = LINEAR_STAGES
  .filter(s => s.key !== MERGED_AWAY_KEY)
  .map(s => (s.key === MERGED_SENT_KEY ? { ...s, label: MERGED_SENT_LABEL } : s));
