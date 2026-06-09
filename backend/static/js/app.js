/* VIP Health Vault — Frontend App */
const API = '';
let token = localStorage.getItem('vhv_token');
let currentUser = JSON.parse(localStorage.getItem('vhv_user') || 'null');
let allRecords = [];
let recordTypes = [];
let mfaRequired = false;

/* -- Particles ---------------------------------------- */
(function initParticles() {
  const c = document.getElementById('particles-canvas');
  const ctx = c.getContext('2d');
  let W, H, particles = [];
  const resize = () => { W = c.width = innerWidth; H = c.height = innerHeight; };
  resize(); window.addEventListener('resize', resize);
  for (let i = 0; i < 60; i++) particles.push({
    x: Math.random()*1920, y: Math.random()*1080,
    vx: (Math.random()-.5)*.3, vy: (Math.random()-.5)*.3,
    r: Math.random()*1.5+.5, a: Math.random()*.4+.1
  });
  (function draw() {
    ctx.clearRect(0,0,W,H);
    particles.forEach(p => {
      p.x += p.vx; p.y += p.vy;
      if (p.x<0) p.x=W; if (p.x>W) p.x=0;
      if (p.y<0) p.y=H; if (p.y>H) p.y=0;
      ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fillStyle=`rgba(201,168,76,${p.a})`; ctx.fill();
    });
    requestAnimationFrame(draw);
  })();
})();

/* -- API Helper --------------------------------------- */
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}

async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers||{}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  
  // CSRF protection: append token header for unsafe methods
  const csrfToken = getCookie('csrf_token');
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }
  
  const res = await fetch(API + path, { ...opts, headers });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.detail || 'An error occurred');
  return json;
}

/* -- Auth -------------------------------------------- */
document.getElementById('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn  = document.getElementById('btn-login');
  const btxt = document.getElementById('btn-login-text');
  const bspin= document.getElementById('btn-login-spin');
  const err  = document.getElementById('login-error');
  err.style.display = 'none';
  btxt.style.display = 'none'; bspin.style.display = 'inline-block';
  btn.disabled = true;
  try {
    const payload = {
      username: document.getElementById('inp-username').value,
      password: document.getElementById('inp-password').value,
    };
    if (mfaRequired) {
      payload.code = document.getElementById('inp-mfa').value;
    }
    
    const data = await apiFetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    
    if (data.mfa_required) {
      mfaRequired = true;
      document.getElementById('login-fields-group').style.display = 'none';
      document.getElementById('inp-username').required = false;
      document.getElementById('inp-password').required = false;
      
      const mfaGroup = document.getElementById('login-mfa-group');
      mfaGroup.style.display = 'block';
      const inpMfa = document.getElementById('inp-mfa');
      inpMfa.required = true;
      inpMfa.value = '';
      inpMfa.focus();
      
      btxt.textContent = 'VERIFY MFA CODE';
      document.getElementById('login-mfa-back').style.display = 'block';
    } else {
      token = data.access_token;
      currentUser = data.user;
      localStorage.setItem('vhv_token', token);
      localStorage.setItem('vhv_user', JSON.stringify(currentUser));
      resetLoginFormState();
      enterApp();
    }
  } catch(ex) {
    err.textContent = ex.message;
    err.style.display = 'block';
  } finally {
    btxt.style.display = 'inline'; bspin.style.display = 'none';
    btn.disabled = false;
  }
});

function fillCreds(u, p) {
  resetLoginFormState();
  document.getElementById('inp-username').value = u;
  document.getElementById('inp-password').value = p;
}

function logout() {
  apiFetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
  token = null; currentUser = null;
  localStorage.removeItem('vhv_token');
  localStorage.removeItem('vhv_user');
  resetLoginFormState();
  document.getElementById('page-login').classList.add('active');
  document.getElementById('page-login').style.display = 'block';
  document.getElementById('page-app').style.display = 'none';
}

function resetLoginForm(e) {
  if (e) e.preventDefault();
  resetLoginFormState();
}

function resetLoginFormState() {
  mfaRequired = false;
  document.getElementById('login-fields-group').style.display = 'block';
  document.getElementById('inp-username').required = true;
  document.getElementById('inp-password').required = true;
  document.getElementById('inp-password').value = '';
  
  const mfaGroup = document.getElementById('login-mfa-group');
  mfaGroup.style.display = 'none';
  const inpMfa = document.getElementById('inp-mfa');
  inpMfa.required = false;
  inpMfa.value = '';
  
  document.getElementById('btn-login-text').textContent = 'ENTER VAULT';
  document.getElementById('login-mfa-back').style.display = 'none';
  document.getElementById('inp-username').focus();
}

/* -- Enter App --------------------------------------- */
function enterApp() {
  document.getElementById('page-login').classList.remove('active');
  document.getElementById('page-login').style.display = 'none';
  document.getElementById('page-app').style.display = 'flex';

  // Sidebar user info
  document.getElementById('sidebar-name').textContent = currentUser.full_name;
  document.getElementById('sidebar-role').textContent = ROLE_LABEL[currentUser.role] || currentUser.role;
  document.getElementById('sidebar-avatar').textContent = currentUser.full_name.charAt(0).toUpperCase();
  document.getElementById('topbar-user-name').textContent = currentUser.full_name;

  // Role-based nav
  if (currentUser.role === 'admin') {
    document.getElementById('nav-users').style.display = 'flex';
    document.getElementById('nav-audit').style.display = 'flex';
  }
  if (currentUser.role === 'vip_patient') document.getElementById('nav-add').style.display = 'none';

  // Pre-fill patient ID for VIP patient
  if (currentUser.role === 'vip_patient') {
    document.getElementById('rec-patient-id').value = currentUser.patient_id || '';
    document.getElementById('rec-patient-id').readOnly = true;
  }

  // Set today's date
  document.getElementById('rec-date').value = new Date().toISOString().split('T')[0];

  loadRecordTypes().then(() => navigate('dashboard'));
}

const ROLE_LABEL = { admin: 'Administrator', doctor: 'Doctor', vip_patient: 'VIP Patient' };

/* -- Auto-login -------------------------------------- */
if (token && currentUser) enterApp();

/* -- System Config & Environment Check ---------------- */
async function checkEnvironment() {
  try {
    const config = await apiFetch('/api/system/config');
    const demoCreds = document.querySelector('.demo-credentials');
    if (demoCreds) {
      if (config.environment === 'development') {
        demoCreds.style.display = 'block';
      } else {
        demoCreds.style.display = 'none';
      }
    }
  } catch(e) {
    console.error("Failed to load system config:", e);
  }
}
checkEnvironment();

/* -- Navigation -------------------------------------- */
function navigate(page) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const view = document.getElementById('view-' + page);
  if (view) view.classList.add('active');
  const navEl = document.querySelector(`[data-page="${page}"]`);
  if (navEl) navEl.classList.add('active');
  const titles = {
    dashboard:      'Dashboard',
    records:        'Health Records',
    'add-record':   'Add Record',
    'chain-status': 'Chain Status',
    vaccines:       'Vaccine Passport',
    medications:    'Medications & Reminders',
    users:          'Users',
    audit:          'Access History',
    security:       'Security Settings',
  };
  document.getElementById('topbar-title').textContent = titles[page] || page;
  if (page === 'dashboard')     loadDashboard();
  if (page === 'records')       loadRecords();
  if (page === 'chain-status')  loadChainStatus();
  if (page === 'vaccines')      loadVaccines();
  if (page === 'medications')   loadMedications();
  if (page === 'users')         loadUsers();
  if (page === 'audit')         switchLogTab(currentLogTab);
  if (page === 'security')      loadSecuritySettings();
}

/* -- Record Types ------------------------------------ */
async function loadRecordTypes() {
  try {
    const d = await apiFetch('/api/record-types');
    recordTypes = d.types;
    const sel = document.getElementById('rec-type');
    d.types.forEach(t => { const o = document.createElement('option'); o.value=t.value; o.textContent=t.label; sel.appendChild(o); });
    const typeFilter = document.getElementById('rec-type-filter');
    d.types.forEach(t => { const o = document.createElement('option'); o.value=t.value; o.textContent=t.label; typeFilter.appendChild(o); });
  } catch(e) { console.error(e); }
}

/* -- Access level helpers ---------------------------- */
const ACCESS_COLORS = { private:'badge-private', doctor_shared:'badge-shared', emergency:'badge-emergency' };
const ACCESS_LABELS = { private:'Patient Only', doctor_shared:'Patient + Doctor', emergency:'Emergency Access' };

/* -- Patient ID helper ------------------------------- */
function patientId() {
  return currentUser.role === 'vip_patient' ? currentUser.patient_id : 'VIP-001';
}

/* -- Dashboard --------------------------------------- */
async function loadDashboard() {
  try {
    const pid = patientId();
    const [recData, statusData] = await Promise.all([
      apiFetch(`/api/records/${pid}`),
      apiFetch(`/api/blockchain/${pid}/status`)
    ]);
    allRecords = recData.records;
    document.getElementById('stat-total-blocks').textContent  = statusData.chain_length;
    document.getElementById('stat-total-records').textContent = recData.records.length;
    const encrypted = recData.records.filter(r => r.is_protected).length;
    document.getElementById('stat-encrypted').textContent = encrypted;
    const valid = statusData.is_valid;
    document.getElementById('stat-integrity').textContent = valid ? 'VALID' : 'BROKEN!';

    // Update integrity icon color
    const iconEl = document.getElementById('stat-integrity-icon');
    if (iconEl) {
      iconEl.querySelector('svg').setAttribute('stroke', valid ? '#2CC985' : '#E57373');
    }

    updateChainPill(valid);
    const recent = recData.records.slice(0, 5);
    document.getElementById('recent-records').innerHTML =
      recent.length ? recent.map(renderRecordCard).join('') : emptyState('No records yet');

    updateClinicalHighlights(recData.records);
  } catch(e) { console.error(e); }
}

function updateClinicalHighlights(records) {
  const highlightDiv = document.getElementById('patient-highlights');
  if (!highlightDiv) return;
  
  highlightDiv.style.display = 'block';

  // 1. Vitals
  const vitalsRecord = records.find(r => r.record_type === 'vital_signs' && !r.is_protected && r.data);
  if (vitalsRecord && vitalsRecord.data && vitalsRecord.data.data) {
    const v = vitalsRecord.data.data;
    document.getElementById('vital-bp-val').textContent = v.blood_pressure || '—';
    document.getElementById('vital-hr-val').textContent = v.heart_rate ? `${v.heart_rate} bpm` : '—';
    document.getElementById('vital-temp-val').textContent = v.temperature ? `${v.temperature} °C` : '—';
    document.getElementById('vital-spo2-val').textContent = v.oxygen_sat ? `${v.oxygen_sat} %` : '—';
    
    const tempVal = parseFloat(v.temperature);
    if (tempVal >= 38.0) {
      document.getElementById('vital-temp-val').style.color = '#ff4d4d';
    } else {
      document.getElementById('vital-temp-val').style.color = '#fff';
    }
    const hrVal = parseInt(v.heart_rate);
    if (hrVal > 100 || hrVal < 60) {
      document.getElementById('vital-hr-val').style.color = '#C9A84C';
    } else {
      document.getElementById('vital-hr-val').style.color = '#fff';
    }
  } else {
    document.getElementById('vital-bp-val').textContent = '—';
    document.getElementById('vital-hr-val').textContent = '—';
    document.getElementById('vital-temp-val').textContent = '—';
    document.getElementById('vital-spo2-val').textContent = '—';
    document.getElementById('vital-temp-val').style.color = '#fff';
    document.getElementById('vital-hr-val').style.color = '#fff';
  }

  // 2. Allergies
  const allergyRecords = records.filter(r => r.record_type === 'allergy' && !r.is_protected && r.data);
  const allergyBox = document.getElementById('allergy-warning-box');
  const allergyUl = document.getElementById('allergy-list-ul');
  
  if (allergyRecords.length > 0) {
    allergyUl.innerHTML = allergyRecords.map(r => {
      const a = r.data.data || {};
      return `<li><strong>${a.allergen || 'Unknown'}</strong>: ${a.reaction || 'No reaction listed'} (${a.severity || 'Mild'} severity, onset: ${a.onset_date || '—'})</li>`;
    }).join('');
    allergyBox.style.display = 'block';
  } else {
    allergyUl.innerHTML = '';
    allergyBox.style.display = 'none';
  }
}

function updateChainPill(valid) {
  const pill = document.getElementById('chain-pill');
  const dot  = pill.querySelector('.chain-dot');
  const txt  = document.getElementById('chain-pill-text');
  pill.className = 'chain-pill' + (valid ? '' : ' invalid');
  dot.className  = 'chain-dot ' + (valid ? 'valid' : 'invalid');
  txt.textContent = valid ? 'Chain Valid' : 'Chain BROKEN!';
}

/* -- Records ----------------------------------------- */
async function loadRecords() {
  const container = document.getElementById('all-records');
  container.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const d = await apiFetch(`/api/records/${patientId()}`);
    allRecords = d.records;
    renderAllRecords();
  } catch(e) { container.innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

function filterRecords() { renderAllRecords(); }

function renderAllRecords() {
  const q    = (document.getElementById('rec-search').value || '').toLowerCase();
  const type = document.getElementById('rec-type-filter').value;
  const filtered = allRecords.filter(r => {
    const d = r.data || {};
    const txt = (r.title + (d.doctor_name||'') + (d.institution||'')).toLowerCase();
    const matchQ = !q || txt.includes(q);
    const matchT = !type || (d.record_type === type);
    return matchQ && matchT;
  });
  document.getElementById('all-records').innerHTML =
    filtered.length ? filtered.map(renderRecordCard).join('') : emptyState('No records found');
}

/* -- Record type labels (no icons) ------------------- */
const TYPE_LABELS = {
  diagnosis:   'Diagnosis',
  lab_result:  'Lab Result',
  prescription:'Prescription',
  surgery:     'Surgery',
  vaccination: 'Vaccination',
  imaging:     'Imaging',
  vital_signs: 'Vital Signs',
  allergy:     'Allergy',
  psychology:  'Psychology',
  genetic:     'Genetics',
  emergency:   'Emergency',
  other:       'Other',
  correction:  'Correction',
  unknown:     'Unknown',
};

function renderRecordCard(r) {
  const d       = r.data || {};
  const type    = d.record_type || 'unknown';
  const typeAbbr = (TYPE_LABELS[type] || type).substring(0, 3).toUpperCase();
  const al      = d.access_level || 'private';
  const date    = d.record_date ? new Date(d.record_date).toLocaleDateString('en-GB') : formatTs(r.timestamp);
  const encBadge  = r.is_protected  ? '<span class="badge badge-encrypted">ENCRYPTED</span>' : '';
  const corrBadge = r.is_correction ? '<span class="badge badge-private">CORRECTION</span>'  : '';
  const typLabel  = recordTypes.find(t => t.value === type)?.label || TYPE_LABELS[type] || type;
  const alBadge   = `<span class="badge ${ACCESS_COLORS[al]||''}">${ACCESS_LABELS[al]||al}</span>`;
  return `
  <div class="record-card ${r.is_protected?'is-encrypted':''} ${r.is_correction?'is-correction':''}"
       onclick="openRecord(${r.block_index})">
    <div class="record-type-icon record-type-text">${typeAbbr}</div>
    <div class="record-main">
      <div class="record-title">${r.title}</div>
      <div class="record-meta">${d.doctor_name||'—'} · ${d.institution||'—'}</div>
      <div class="record-badges">${alBadge}${encBadge}${corrBadge}
        <span class="badge badge-private" style="background:rgba(255,255,255,0.05);color:var(--muted)">${typLabel}</span>
      </div>
    </div>
    <div class="record-right">
      <div class="record-date">${date}</div>
      <div class="record-hash">#${r.block_index} · ${r.hash_preview}</div>
    </div>
  </div>`;
}

function emptyState(msg) {
  return `<div class="empty-state"><div class="empty-icon-svg">
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#6B6882" stroke-width="1" stroke-linecap="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
    </svg>
  </div><p>${msg}</p></div>`;
}

/* -- Record Detail Modal ----------------------------- */
function renderAttachmentHtml(fileName, fileType, fileData) {
  if (!fileData) return '';

  let previewHtml = '';
  if (fileType && fileType.startsWith('image/')) {
    previewHtml = `
      <div style="margin-top: 14px; border: 1px solid var(--border); border-radius: 6px; padding: 10px; background: rgba(255,255,255,0.02);">
        <div style="font-size:11px; color:var(--muted); margin-bottom:8px;">IMAGE ATTACHMENT: ${fileName}</div>
        <img src="data:${fileType};base64,${fileData}" style="max-width:100%; max-height:240px; border-radius:4px; display:block; margin:0 auto;" />
        <button class="btn btn-gold btn-sm" style="margin-top:10px; width:100%" onclick="downloadBase64File('${fileName}', '${fileType}', '${fileData}')">Download Image</button>
      </div>
    `;
  } else {
    previewHtml = `
      <div style="margin-top: 14px; border: 1px solid var(--border); border-radius: 6px; padding: 12px; background: rgba(255,255,255,0.02); display:flex; justify-content:space-between; align-items:center;">
        <div style="text-align:left">
          <div style="font-weight:600; font-size:13px; color:#fff;">📄 ${fileName}</div>
          <div style="font-size:11px; color:var(--muted); margin-top:2px;">Type: ${fileType || 'Unknown'}</div>
        </div>
        <button class="btn btn-gold btn-sm" onclick="downloadBase64File('${fileName}', '${fileType}', '${fileData}')">Download File</button>
      </div>
    `;
  }
  return `<hr style="border-color:var(--border);margin:16px 0"><h4 style="color:var(--muted-hi);font-size:12px;margin-bottom:12px">ATTACHMENT</h4>${previewHtml}`;
}

function downloadBase64File(fileName, fileType, fileData) {
  const linkSource = `data:${fileType};base64,${fileData}`;
  const downloadLink = document.createElement("a");
  downloadLink.href = linkSource;
  downloadLink.download = fileName;
  downloadLink.click();
}

async function openRecord(idx) {
  const r = allRecords.find(x => x.block_index === idx);
  if (!r) return;

  if (r.is_protected) {
    document.getElementById('modal-content').innerHTML = `
      <h2 style="font-size:20px;font-weight:700;margin-bottom:20px">Encrypted VIP Record</h2>
      <p style="margin-bottom:16px;color:var(--muted)">This record is encrypted with AES-256. Enter the password to decrypt:</p>
      <div id="modal-decrypt-error" class="alert alert-error" style="display:none;margin-bottom:12px"></div>
      <div class="field-group">
        <label>Record Password</label>
        <div class="input-wrap">
          <input type="password" id="modal-decrypt-password" placeholder="••••••••" style="width:100%;margin-bottom:12px;padding:8px 12px;border-radius:4px;border:1px solid var(--border);background:rgba(255,255,255,0.05);color:white;" />
        </div>
      </div>
      <button class="btn btn-gold btn-full" onclick="decryptRecord(${idx})">Decrypt &amp; View</button>
      <hr style="border-color:var(--border);margin:16px 0">
      <div class="modal-field"><div class="modal-field-label">Block #</div><div class="modal-field-value">${r.block_index}</div></div>
      <div class="modal-field"><div class="modal-field-label">Block Hash</div><div class="modal-field-value mono">${r.hash_preview}</div></div>
    `;
    document.getElementById('modal-overlay').classList.add('open');
    return;
  }

  const d = r.data || {};
  const typLabel = recordTypes.find(t => t.value === d.record_type)?.label || d.record_type || '—';

  let dataFields = '';
  if (d.data && typeof d.data === 'object') {
    dataFields = Object.entries(d.data).map(([k,v]) =>
      `<div class="modal-field"><div class="modal-field-label">${k}</div><div class="modal-field-value">${v}</div></div>`
    ).join('');
  }

  const attachmentHtml = renderAttachmentHtml(r.file_name, r.file_type, r.file_data);

  document.getElementById('modal-content').innerHTML = `
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px">${r.title}</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
      <div class="modal-field"><div class="modal-field-label">Block #</div><div class="modal-field-value">${r.block_index}</div></div>
      <div class="modal-field"><div class="modal-field-label">Record Type</div><div class="modal-field-value">${typLabel}</div></div>
      <div class="modal-field"><div class="modal-field-label">Doctor</div><div class="modal-field-value">${d.doctor_name||'—'}</div></div>
      <div class="modal-field"><div class="modal-field-label">Institution</div><div class="modal-field-value">${d.institution||'—'}</div></div>
      <div class="modal-field"><div class="modal-field-label">Date</div><div class="modal-field-value">${d.record_date||'—'}</div></div>
      <div class="modal-field"><div class="modal-field-label">Access</div><div class="modal-field-value">${ACCESS_LABELS[d.access_level]||d.access_level||'—'}</div></div>
    </div>
    ${dataFields ? `<hr style="border-color:var(--border);margin:16px 0"><h4 style="color:var(--muted-hi);font-size:12px;margin-bottom:12px">DATA FIELDS</h4><div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">${dataFields}</div>` : ''}
    ${d.notes ? `<div class="modal-field" style="margin-top:14px"><div class="modal-field-label">Notes</div><div class="modal-field-value">${d.notes}</div></div>` : ''}
    ${attachmentHtml}
    <hr style="border-color:var(--border);margin:16px 0">
    <div class="modal-field"><div class="modal-field-label">Block Hash</div><div class="modal-field-value mono">${r.hash_preview}</div></div>
    <div class="modal-field"><div class="modal-field-label">Created By</div><div class="modal-field-value">${d.created_by||'—'}</div></div>
  `;
  document.getElementById('modal-overlay').classList.add('open');
}

async function decryptRecord(idx) {
  const pwdEl = document.getElementById('modal-decrypt-password');
  const errEl = document.getElementById('modal-decrypt-error');
  if (!pwdEl) return;
  const pwd = pwdEl.value;
  if (!pwd) {
    errEl.textContent = 'Please enter the password.';
    errEl.style.display = 'block';
    return;
  }
  errEl.style.display = 'none';

  try {
    const res = await apiFetch(`/api/records/${patientId()}/${idx}/decrypt`, {
      method: 'POST',
      body: JSON.stringify({ password: pwd })
    });
    const decData = res.data;

    const r = allRecords.find(x => x.block_index === idx);
    const d = decData || {};
    const typLabel = recordTypes.find(t => t.value === d.record_type)?.label || d.record_type || '—';

    let dataFields = '';
    if (d.data && typeof d.data === 'object') {
      dataFields = Object.entries(d.data).map(([k,v]) =>
        `<div class="modal-field"><div class="modal-field-label">${k}</div><div class="modal-field-value">${v}</div></div>`
      ).join('');
    }

    const attachmentHtml = renderAttachmentHtml(d.file_name, d.file_type, d.file_data);

    document.getElementById('modal-content').innerHTML = `
      <h2 style="font-size:20px;font-weight:700;margin-bottom:20px">${d.title || (r ? r.title : '')}</h2>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <div class="modal-field"><div class="modal-field-label">Block #</div><div class="modal-field-value">${idx}</div></div>
        <div class="modal-field"><div class="modal-field-label">Record Type</div><div class="modal-field-value">${typLabel}</div></div>
        <div class="modal-field"><div class="modal-field-label">Doctor</div><div class="modal-field-value">${d.doctor_name||'—'}</div></div>
        <div class="modal-field"><div class="modal-field-label">Institution</div><div class="modal-field-value">${d.institution||'—'}</div></div>
        <div class="modal-field"><div class="modal-field-label">Date</div><div class="modal-field-value">${d.record_date||'—'}</div></div>
        <div class="modal-field"><div class="modal-field-label">Access</div><div class="modal-field-value">${ACCESS_LABELS[d.access_level]||d.access_level||'—'}</div></div>
      </div>
      ${dataFields ? `<hr style="border-color:var(--border);margin:16px 0"><h4 style="color:var(--muted-hi);font-size:12px;margin-bottom:12px">DATA FIELDS</h4><div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">${dataFields}</div>` : ''}
      ${d.notes ? `<div class="modal-field" style="margin-top:14px"><div class="modal-field-label">Notes</div><div class="modal-field-value">${d.notes}</div></div>` : ''}
      ${attachmentHtml}
      <hr style="border-color:var(--border);margin:16px 0">
      <div class="modal-field"><div class="modal-field-label">Block Hash</div><div class="modal-field-value mono">${r ? r.hash_preview : '—'}</div></div>
      <div class="modal-field"><div class="modal-field-label">Created By</div><div class="modal-field-value">${d.created_by||'—'}</div></div>
    `;
  } catch (ex) {
    errEl.textContent = ex.message;
    errEl.style.display = 'block';
  }
}

function closeModal() { document.getElementById('modal-overlay').classList.remove('open'); }

/* -- Add Record Form --------------------------------- */
const DYNAMIC_FIELDS = {
  diagnosis:    [{id:'icd_code',label:'ICD Code'},{id:'severity',label:'Severity (Mild/Moderate/Severe)'},{id:'symptoms',label:'Symptoms'}],
  lab_result:   [{id:'test_name',label:'Test Name'},{id:'result_value',label:'Result Value'},{id:'reference_range',label:'Reference Range'},{id:'unit',label:'Unit'}],
  prescription: [{id:'medication',label:'Medication Name'},{id:'dose',label:'Dose'},{id:'frequency',label:'Frequency'},{id:'duration',label:'Duration (days)'}],
  surgery:      [{id:'procedure',label:'Procedure'},{id:'anesthesia',label:'Anesthesia Type'},{id:'duration_min',label:'Duration (min)'},{id:'outcome',label:'Outcome'}],
  vaccination:  [{id:'vaccine_name',label:'Vaccine Name'},{id:'lot_number',label:'Lot Number'},{id:'dose_number',label:'Dose Number'},{id:'next_dose',label:'Next Dose Date'}],
  imaging:      [{id:'modality',label:'Modality (MRI/CT/X-Ray)'},{id:'body_part',label:'Body Part'},{id:'findings',label:'Findings'},{id:'radiologist',label:'Radiologist'}],
  vital_signs:  [{id:'blood_pressure',label:'Blood Pressure (mmHg)'},{id:'heart_rate',label:'Heart Rate (bpm)'},{id:'temperature',label:'Temperature (C)'},{id:'oxygen_sat',label:'SpO2 (%)'}],
  allergy:      [{id:'allergen',label:'Allergen'},{id:'reaction',label:'Reaction Type'},{id:'severity',label:'Severity'},{id:'onset_date',label:'Onset Date'}],
};

function renderDynamicFields() {
  const type = document.getElementById('rec-type').value;
  const container = document.getElementById('dynamic-fields');
  const fields = DYNAMIC_FIELDS[type] || [];
  container.innerHTML = fields.map(f =>
    `<div class="field-group">
      <label>${f.label}</label>
      <input type="text" id="dyn-${f.id}" placeholder="${f.label}...">
    </div>`
  ).join('');
}

document.getElementById('add-record-form').addEventListener('submit', async e => {
  e.preventDefault();
  const errEl = document.getElementById('add-error');
  const okEl  = document.getElementById('add-success');
  errEl.style.display = 'none'; okEl.style.display = 'none';

  const type          = document.getElementById('rec-type').value;
  const isConfidential = document.getElementById('rec-confidential').checked;
  const confPassword   = document.getElementById('rec-confidential-password').value.trim();

  // S-04 FIX: validate confidential password before submitting
  if (isConfidential && !confPassword) {
    errEl.textContent = 'A password is required for confidential (encrypted) records.';
    errEl.style.display = 'block';
    return;
  }

  const dynData = {};
  (DYNAMIC_FIELDS[type]||[]).forEach(f => {
    const el = document.getElementById('dyn-'+f.id);
    if (el && el.value.trim()) dynData[f.id] = el.value.trim();
  });

  const fileInput = document.getElementById('rec-file');
  let file_name = null;
  let file_type = null;
  let file_data = null;

  if (fileInput && fileInput.files && fileInput.files.length > 0) {
    const file = fileInput.files[0];
    if (file.size > 2 * 1024 * 1024) {
      errEl.textContent = 'Attachment size exceeds the 2MB limit.';
      errEl.style.display = 'block';
      return;
    }
    file_name = file.name;
    file_type = file.type;

    const getBase64 = (f) => new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(f);
      reader.onload = () => resolve(reader.result);
      reader.onerror = error => reject(error);
    });

    try {
      const dataUrl = await getBase64(file);
      file_data = dataUrl.split(',')[1];
    } catch(err) {
      errEl.textContent = 'Failed to read file attachment.';
      errEl.style.display = 'block';
      return;
    }
  }

  const payload = {
    patient_id:             document.getElementById('rec-patient-id').value.trim(),
    record_type:            type,
    title:                  document.getElementById('rec-title').value.trim(),
    doctor_name:            document.getElementById('rec-doctor').value.trim(),
    institution:            document.getElementById('rec-institution').value.trim(),
    record_date:            document.getElementById('rec-date').value,
    access_level:           document.getElementById('rec-access').value,
    is_confidential:        isConfidential,
    confidential_password:  isConfidential ? confPassword : null,  // S-04 FIX
    data:                   dynData,
    notes:                  document.getElementById('rec-notes').value.trim(),
    file_name:              file_name,
    file_type:              file_type,
    file_data:              file_data,
  };

  const btn = document.getElementById('btn-add-rec');
  btn.disabled = true; btn.textContent = 'Saving...';
  try {
    const res = await apiFetch('/api/records', { method:'POST', body: JSON.stringify(payload) });
    okEl.textContent = `${res.message} (Block #${res.block_index})`;
    okEl.style.display = 'block';
    document.getElementById('add-record-form').reset();
    document.getElementById('dynamic-fields').innerHTML = '';
    // Reset file input
    if (fileInput) fileInput.value = '';
    // Reset confidential password field and hide it
    document.getElementById('rec-confidential-password').value = '';
    document.getElementById('confidential-password-group').style.display = 'none';
    if (currentUser.role === 'vip_patient') document.getElementById('rec-patient-id').value = currentUser.patient_id || '';
    document.getElementById('rec-date').value = new Date().toISOString().split('T')[0];
  } catch(ex) {
    errEl.textContent = ex.message; errEl.style.display = 'block';
  } finally {
    btn.disabled = false; btn.textContent = 'Save to Blockchain';
  }
});

/* -- Confidential Checkbox Toggle -------------------- */
document.getElementById('rec-confidential').addEventListener('change', function() {
  const group = document.getElementById('confidential-password-group');
  group.style.display = this.checked ? 'block' : 'none';
  if (!this.checked) document.getElementById('rec-confidential-password').value = '';
});

/* -- Chain Status ------------------------------------ */
async function loadChainStatus() {
  const box = document.getElementById('chain-status-content');
  const vis = document.getElementById('chain-visual');
  box.innerHTML = '<div class="loading-spinner">Verifying chain...</div>';
  vis.innerHTML = '';
  try {
    const pid = patientId();
    const [status, records] = await Promise.all([
      apiFetch(`/api/blockchain/${pid}/status`),
      apiFetch(`/api/records/${pid}`)
    ]);
    const valid = status.is_valid;
    updateChainPill(valid);
    box.innerHTML = `
      <div class="chain-stat"><div class="chain-stat-val">${status.chain_length}</div><div class="chain-stat-lbl">Total Blocks</div></div>
      <div class="chain-stat">
        <div class="chain-stat-val" style="color:${valid?'var(--success)':'var(--danger)'}; font-size:18px; font-weight:700">
          ${valid ? 'VALID' : 'BROKEN'}
        </div>
        <div class="chain-stat-lbl">Integrity</div>
      </div>
      <div class="chain-stat">
        <div class="chain-stat-val" style="color:${valid?'var(--success)':'var(--danger);font-size:20px'}">
          ${valid ? '100%' : 'ERROR #' + status.broken_at}
        </div>
        <div class="chain-stat-lbl">Status</div>
      </div>`;

    // Visual chain (show last 8 blocks)
    const recs = records.records.slice(0, 8);
    recs.forEach((r, i) => {
      const broken = status.broken_at !== null && r.block_index >= status.broken_at;
      vis.innerHTML += `
        <div class="chain-block-viz ${broken?'broken-block':'valid-block'}">
          <div class="blk-header">BLOCK #${r.block_index} · ${formatTs(r.timestamp)}</div>
          <div class="blk-hash">${r.hash_preview}</div>
          <div style="margin-top:4px;font-size:11px;color:var(--muted)">${r.title}</div>
        </div>
        ${i < recs.length-1 ? '<div class="chain-connector"></div>' : ''}`;
    });
  } catch(e) { box.innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

/* -- Admin Users ------------------------------------- */
async function loadUsers() {
  const container = document.getElementById('users-list');
  container.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const d = await apiFetch('/api/admin/users');
    container.innerHTML = d.users.map(u => `
      <div class="user-card glass">
        <div class="user-avatar" style="background:linear-gradient(135deg,#C9A84C,#8B6914)">${u.full_name.charAt(0)}</div>
        <div style="flex:1">
          <div style="font-weight:600">${u.full_name}</div>
          <div style="font-size:12px;color:var(--muted)">@${u.username} · ${u.patient_id||'no patient ID'}</div>
        </div>
        <span class="role-badge badge-${u.role==='admin'?'admin':u.role==='doctor'?'doctor':'vip'}">${ROLE_LABEL[u.role]||u.role}</span>
      </div>`
    ).join('');
  } catch(e) { container.innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

/* -- Helpers ----------------------------------------- */
function formatTs(ts) {
  return new Date(ts * 1000).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric' });
}

function formatTsFull(ts) {
  return new Date(ts * 1000).toLocaleString('en-GB', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit' });
}

/* -- Audit Log --------------------------------------- */
async function loadAuditLog() {
  const container = document.getElementById('audit-list');
  container.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const pid = patientId();
    const d = await apiFetch(`/api/blockchain/${pid}/audit?limit=100`);
    if (!d.logs || d.logs.length === 0) {
      container.innerHTML = emptyState('No audit records yet');
      return;
    }
    container.innerHTML = d.logs.map(log => {
      const isAlert = log.action.includes('FAILED');
      const statusLabel = isAlert ? 'WARNING' : 'OK';
      return `
      <div class="record-card ${isAlert ? 'is-encrypted' : ''}" style="cursor:default">
        <div class="record-type-icon record-type-text">${log.action.substring(0,3)}</div>
        <div class="record-main">
          <div class="record-title">${log.action.replace(/_/g, ' ')}</div>
          <div class="record-meta">User: <strong>${log.username}</strong> · Block: ${log.block_index !== null ? '#'+log.block_index : '—'}</div>
          <div class="record-meta" style="font-family:monospace;font-size:11px;color:var(--muted)">Device: ${(log.device_id||'?').substring(0,16)}...</div>
        </div>
        <div class="record-right">
          <div class="record-date">${formatTsFull(log.timestamp)}</div>
          <div class="record-hash" style="color:${isAlert?'var(--danger)':'var(--success)'}">${statusLabel}</div>
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    container.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

let currentLogTab = 'audit';

function switchLogTab(tab) {
  currentLogTab = tab;
  const auditList  = document.getElementById('audit-list');
  const accessList = document.getElementById('access-log-list');
  const btnAudit   = document.getElementById('btn-audit-tab');
  const btnAccess  = document.getElementById('btn-access-tab');

  if (tab === 'audit') {
    auditList.style.display  = 'block';
    accessList.style.display = 'none';
    btnAudit.className  = 'btn btn-gold btn-sm';
    btnAccess.className = 'btn btn-ghost btn-sm';
    loadAuditLog();
  } else {
    auditList.style.display  = 'none';
    accessList.style.display = 'block';
    btnAudit.className  = 'btn btn-ghost btn-sm';
    btnAccess.className = 'btn btn-gold btn-sm';
    loadAccessLogs();
  }
}

async function loadAccessLogs() {
  const container = document.getElementById('access-log-list');
  container.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const pid = patientId();
    const d = await apiFetch(`/api/blockchain/${pid}/access-logs?limit=100`);
    if (!d.logs || d.logs.length === 0) {
      container.innerHTML = emptyState('No access log entries yet');
      return;
    }
    container.innerHTML = d.logs.map(log => {
      const isAlert = log.action.includes('FAILED');
      const statusLabel = isAlert ? 'WARNING' : 'ACCESS';
      return `
      <div class="record-card ${isAlert ? 'is-encrypted' : ''}" style="cursor:default">
        <div class="record-type-icon record-type-text">${log.action.substring(0,3)}</div>
        <div class="record-main">
          <div class="record-title">${log.action.replace(/_/g, ' ')}</div>
          <div class="record-meta">User: <strong>${log.username}</strong> · Block: ${log.block_index !== undefined && log.block_index !== null ? '#'+log.block_index : '—'}</div>
          <div class="record-meta" style="font-family:monospace;font-size:11px;color:var(--muted)">Device: ${(log.device_id||'?').substring(0,16)}...</div>
        </div>
        <div class="record-right">
          <div class="record-date">${formatTsFull(log.timestamp)}</div>
          <div class="record-hash" style="color:${isAlert?'var(--danger)':'var(--success)'}">${statusLabel}</div>
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    container.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

function refreshLogPage() {
  if (currentLogTab === 'audit') loadAuditLog();
  else loadAccessLogs();
}

/* -- Security & 2FA ---------------------------------- */
async function loadSecuritySettings() {
  const err = document.getElementById('security-error');
  const succ = document.getElementById('security-success');
  err.style.display = 'none';
  succ.style.display = 'none';
  
  try {
    const me = await apiFetch('/api/auth/me');
    currentUser.totp_enabled = me.totp_enabled;
    localStorage.setItem('vhv_user', JSON.stringify(currentUser));
    
    const statusBox = document.getElementById('mfa-status-box');
    const setupSec = document.getElementById('mfa-setup-section');
    const disableSec = document.getElementById('mfa-disable-section');
    
    if (me.totp_enabled) {
      statusBox.innerHTML = `
        <div class="status-badge enabled">
          <span class="chain-dot valid"></span>
          <span>Two-Factor Authentication is ENABLED</span>
        </div>
      `;
      setupSec.style.display = 'none';
      disableSec.style.display = 'block';
      document.getElementById('inp-2fa-disable-code').value = '';
    } else {
      statusBox.innerHTML = `
        <div class="status-badge disabled" style="margin-bottom:18px; display:flex;">
          <span class="chain-dot invalid"></span>
          <span>Two-Factor Authentication is DISABLED</span>
        </div>
        <div style="margin-top:10px;">
          <button class="btn btn-gold" onclick="setup2FA()">Set Up Authenticator App</button>
        </div>
      `;
      setupSec.style.display = 'none';
      disableSec.style.display = 'none';
    }
  } catch(e) {
    err.textContent = e.message;
    err.style.display = 'block';
  }
}

async function setup2FA() {
  const err = document.getElementById('security-error');
  err.style.display = 'none';
  
  try {
    const res = await apiFetch('/api/auth/2fa/setup', { method: 'POST' });
    document.getElementById('mfa-qr-code-img').src = res.qr_code;
    document.getElementById('mfa-secret-key').textContent = res.secret;
    document.getElementById('mfa-setup-section').style.display = 'block';
    document.getElementById('inp-2fa-verify-code').value = '';
    document.getElementById('inp-2fa-verify-code').focus();
  } catch(e) {
    err.textContent = e.message;
    err.style.display = 'block';
  }
}

async function enable2FA() {
  const err = document.getElementById('security-error');
  const succ = document.getElementById('security-success');
  err.style.display = 'none';
  succ.style.display = 'none';
  
  const code = document.getElementById('inp-2fa-verify-code').value.trim();
  if (!code) {
    err.textContent = 'Please enter verification code.';
    err.style.display = 'block';
    return;
  }
  
  try {
    const res = await apiFetch('/api/auth/2fa/enable', {
      method: 'POST',
      body: JSON.stringify({ code })
    });
    succ.textContent = res.message;
    succ.style.display = 'block';
    
    await loadSecuritySettings();
  } catch(e) {
    err.textContent = e.message;
    err.style.display = 'block';
  }
}

async function disable2FA() {
  const err = document.getElementById('security-error');
  const succ = document.getElementById('security-success');
  err.style.display = 'none';
  succ.style.display = 'none';
  
  const code = document.getElementById('inp-2fa-disable-code').value.trim();
  if (!code) {
    err.textContent = 'Please enter validation code to disable 2FA.';
    err.style.display = 'block';
    return;
  }
  
  try {
    const res = await apiFetch('/api/auth/2fa/disable', {
      method: 'POST',
      body: JSON.stringify({ code })
    });
    succ.textContent = res.message;
    succ.style.display = 'block';
    
    await loadSecuritySettings();
  } catch(e) {
    err.textContent = e.message;
    err.style.display = 'block';
  }
}

async function loadVaccines() {
  const container = document.getElementById('vaccine-passport-list');
  container.innerHTML = '<div class="loading-spinner">Loading Vaccine Passport...</div>';
  try {
    const pid = patientId();
    const d = await apiFetch(`/api/records/${pid}`);
    allRecords = d.records;
    
    const vaccines = allRecords.filter(r => r.record_type === 'vaccination' || (r.is_protected && r.title === 'ENCRYPTED VIP RECORD'));
    if (vaccines.length === 0) {
      container.innerHTML = emptyState('No vaccination records found in the blockchain registry.');
      return;
    }
    
    container.innerHTML = `
      <div class="glass" style="padding: 20px; border-radius: 8px; margin-bottom: 20px; overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; text-align: left; color: #fff;">
          <thead>
            <tr style="border-bottom: 1px solid var(--border); color: var(--muted-hi); font-size: 13px;">
              <th style="padding: 12px 8px;">Vaccine Name</th>
              <th style="padding: 12px 8px;">Lot Number</th>
              <th style="padding: 12px 8px;">Dose #</th>
              <th style="padding: 12px 8px;">Date Administered</th>
              <th style="padding: 12px 8px;">Next Dose Due</th>
              <th style="padding: 12px 8px;">Status</th>
            </tr>
          </thead>
          <tbody>
            ${vaccines.map(r => {
              if (r.is_protected) {
                return `
                  <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 13px; cursor: pointer;" onclick="openRecord(${r.block_index})">
                    <td colspan="5" style="padding: 14px 8px; color: var(--muted); font-style: italic;">🔐 Confidential Block #${r.block_index} — Click to decrypt in Records</td>
                    <td style="padding: 14px 8px;"><span class="badge badge-encrypted">Encrypted</span></td>
                  </tr>
                `;
              }
              const val = r.data || {};
              const dateStr = val.record_date ? new Date(val.record_date).toLocaleDateString('en-GB') : '—';
              const nextDose = val.data && val.data.next_dose ? new Date(val.data.next_dose).toLocaleDateString('en-GB') : '—';
              return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 13px; cursor: pointer;" onclick="openRecord(${r.block_index})">
                  <td style="padding: 14px 8px; font-weight: 600;">${val.data.vaccine_name || '—'}</td>
                  <td style="padding: 14px 8px; font-family: var(--font-mono);">${val.data.lot_number || '—'}</td>
                  <td style="padding: 14px 8px;">Dose ${val.data.dose_number || '1'}</td>
                  <td style="padding: 14px 8px;">${dateStr}</td>
                  <td style="padding: 14px 8px;">${nextDose}</td>
                  <td style="padding: 14px 8px;"><span class="badge badge-shared">Verified</span></td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;
  } catch(e) {
    container.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

async function loadMedications() {
  const container = document.getElementById('active-medications-list');
  container.innerHTML = '<div class="loading-spinner">Loading Active Medications...</div>';
  try {
    const pid = patientId();
    const d = await apiFetch(`/api/records/${pid}`);
    allRecords = d.records;
    
    const prescriptions = allRecords.filter(r => r.record_type === 'prescription' || (r.is_protected && r.title === 'ENCRYPTED VIP RECORD'));
    if (prescriptions.length === 0) {
      container.innerHTML = emptyState('No active medications or prescriptions found.');
      return;
    }
    
    const activeList = [];
    const expiredList = [];
    
    prescriptions.forEach(r => {
      if (r.is_protected) {
        activeList.push(r);
        return;
      }
      
      const val = r.data || {};
      const recordDate = new Date(val.record_date);
      const durationDays = parseInt(val.data.duration || 0);
      const expiryDate = new Date(recordDate.getTime() + durationDays * 24 * 60 * 60 * 1000);
      const today = new Date();
      today.setHours(0,0,0,0);
      expiryDate.setHours(0,0,0,0);
      
      const details = {
        block_index: r.block_index,
        title: r.title,
        medication: val.data.medication || 'Unknown',
        dose: val.data.dose || '—',
        frequency: val.data.frequency || '—',
        duration: durationDays,
        instructions: val.data.instructions || '—',
        record_date: val.record_date,
        doctor: val.doctor_name,
        expiry_date: expiryDate.toLocaleDateString('en-GB'),
        is_protected: false
      };
      
      if (expiryDate >= today) {
        activeList.push(details);
      } else {
        expiredList.push(details);
      }
    });
    
    let activeHtml = '';
    if (activeList.length === 0) {
      activeHtml = '<p style="color:var(--muted); font-size:13px; font-style:italic; margin-bottom: 24px;">No currently active medications.</p>';
    } else {
      activeHtml = `
        <h3 style="color:#C9A84C; font-size:16px; font-weight:700; margin-bottom:14px;">⚡ CURRENT ACTIVE MEDICATIONS:</h3>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px; margin-bottom:32px;">
          ${activeList.map(m => {
            if (m.is_protected) {
              return `
                <div class="stat-card glass" style="border-left:3px solid var(--gold); cursor:pointer" onclick="openRecord(${m.block_index})">
                  <div class="stat-info">
                    <div class="stat-value" style="font-size:14px; font-weight:600; color:#fff;">🔐 Decrypt Protected Prescription</div>
                    <div class="stat-label" style="font-size:11px; margin-top:4px;">Block #${m.block_index}</div>
                  </div>
                </div>
              `;
            }
            return `
              <div class="stat-card glass" style="border-left:3px solid #10b981; display:flex; flex-direction:column; justify-content:space-between; align-items:flex-start;">
                <div style="width:100%">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:700; font-size:16px; color:#fff;">${m.medication}</span>
                    <span class="badge badge-shared" style="background:rgba(16,185,129,0.1); color:#10b981; border: 1px solid rgba(16,185,129,0.3)">ACTIVE</span>
                  </div>
                  <div style="font-size:12px; color:var(--muted-hi); margin-top:8px;">
                    <strong>Dosage:</strong> ${m.dose} · <strong>Frequency:</strong> ${m.frequency}
                  </div>
                  <div style="font-size:12px; color:var(--muted); margin-top:4px;">
                    <strong>Instructions:</strong> ${m.instructions}
                  </div>
                </div>
                <div style="width:100%; border-top:1px solid rgba(255,255,255,0.05); margin-top:12px; padding-top:8px; display:flex; justify-content:space-between; align-items:center; font-size:11px; color:var(--muted)">
                  <span>Expires: <strong>${m.expiry_date}</strong></span>
                  <span>Dr. ${m.doctor}</span>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      `;
    }

    let expiredHtml = '';
    if (expiredList.length > 0) {
      expiredHtml = `
        <h3 style="color:var(--muted-hi); font-size:15px; font-weight:600; margin-bottom:14px;">⌛ EXPIRED PRESCRIPTIONS HISTORY:</h3>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px;">
          ${expiredList.map(m => `
            <div class="stat-card glass" style="border-left:3px solid var(--border); opacity:0.6; display:flex; flex-direction:column; justify-content:space-between; align-items:flex-start;">
              <div style="width:100%">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-weight:700; font-size:15px; color:var(--muted-hi);">${m.medication}</span>
                  <span class="badge badge-private" style="background:rgba(255,255,255,0.05); color:var(--muted)">EXPIRED</span>
                </div>
                <div style="font-size:12px; color:var(--muted); margin-top:8px;">
                  <strong>Dosage:</strong> ${m.dose} · <strong>Frequency:</strong> ${m.frequency}
                </div>
              </div>
              <div style="width:100%; border-top:1px solid rgba(255,255,255,0.05); margin-top:12px; padding-top:8px; display:flex; justify-content:space-between; align-items:center; font-size:11px; color:var(--muted)">
                <span>Expired on: <strong>${m.expiry_date}</strong></span>
                <span>Dr. ${m.doctor}</span>
              </div>
            </div>
          `).join('')}
        </div>
      `;
    }

    container.innerHTML = activeHtml + expiredHtml;
  } catch(e) {
    container.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}
