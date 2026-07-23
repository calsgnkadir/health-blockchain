import { API, apiFetch, patientId, formatTs, formatTsFull, emptyState, ROLE_LABEL, getCurrentUser, appState } from './modules/utils.js';
import { mfaRequired, resetLoginFormState, resetLoginForm, fillCreds, logout, setup2FA, enable2FA, disable2FA, initAuthListeners, loginWithWeb3Wallet, loginWithPasskey, registerPasskey, showEmergencyQR, revokeEmergencyQR, closeEmergencyQR, showDeadManModal, sendDeadManPing, saveDeadManConfig, closeDeadManModal } from './modules/auth.js';
import { updateChainPill, updateClinicalHighlights, renderVitalsChart, loadDashboard, navigate } from './modules/dashboard.js';
import { allRecords, recordTypes, loadRecordTypes, loadRecords, filterRecords, renderAllRecords, renderRecordCard, renderAttachmentHtml, downloadBase64File, downloadOffchainFile, openRecord, decryptRecord, closeModal, DYNAMIC_FIELDS, renderDynamicFields, zoomDicom, invertDicom, resetDicom, initRecordsListeners, startAddingDicomAnnotation, deleteDicomAnnotation, setDicomLevel, setDicomWidth } from './modules/records.js';
import { getNotifications, addNotification, updateNotificationsUI, toggleNotifications, closeAllDropdowns, markAsRead, markAllAsRead, clearAllNotifications } from './modules/notifications.js';
import { loadConsents, grantConsent, revokeConsent, triggerBreakGlass } from './modules/consent.js';
import { loadAppointments, showBookAppointmentModal, bookAppointment, cancelAppointment } from './modules/appointments.js';
import { loadTriage, sendTriageSymptom } from './modules/triage.js';
import { loadChainStatus } from './modules/blockchain.js';

/* -- Particle Background Canvas ---------------------------------------- */
(function initParticles() {
  const c = document.getElementById('particles-canvas');
  if (!c) return;
  const ctx = c.getContext('2d');
  let W, H, particles = [];
  const resize = () => { W = c.width = window.innerWidth; H = c.height = window.innerHeight; };
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

/* -- Enter App Initialization --------------------------------------- */
window.enterApp = function() {
  const currentUser = getCurrentUser();
  if (!currentUser) return;

  const pageLogin = document.getElementById('page-login');
  if (pageLogin) {
    pageLogin.classList.remove('active');
    pageLogin.style.display = 'none';
  }
  const pageApp = document.getElementById('page-app');
  if (pageApp) pageApp.style.display = 'flex';

  // Use centralized state manager
  appState.updateUser(currentUser);

  // Pre-fill patient ID for VIP patient
  const recPatId = document.getElementById('rec-patient-id');
  if (recPatId) {
    if (currentUser.role === 'vip_patient') {
      recPatId.value = currentUser.patient_id || '';
      recPatId.readOnly = true;
    } else {
      recPatId.value = 'VIP-001';
      recPatId.readOnly = false;
    }
  }

  // Set today's date
  const recDate = document.getElementById('rec-date');
  if (recDate) recDate.value = new Date().toISOString().split('T')[0];

  updateNotificationsUI();
  addNotification('System Login', `Access granted to user ${currentUser.username}. Device Fingerprint verified.`, 'success');

  loadRecordTypes().then(() => navigate('dashboard'));
};

/* -- Page-Specific View Handlers (Remaining from Monolith) ----------- */
window.loadVaccines = async function() {
  const container = document.getElementById('vaccine-passport-list');
  if (!container) return;
  container.innerHTML = '<div class="loading-spinner">Loading Vaccine Passport...</div>';
  try {
    const pid = patientId();
    const d = await apiFetch(`/api/records/${pid}`);
    const vaccines = d.records.filter(r => r.record_type === 'vaccination' || (r.is_protected && r.title === 'ENCRYPTED VIP RECORD'));
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
                  <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 13px; cursor: pointer;" onclick="window.openRecord(${r.block_index})">
                    <td colspan="5" style="padding: 14px 8px; color: var(--muted); font-style: italic;">🔐 Confidential Block #${r.block_index} — Click to decrypt in Records</td>
                    <td style="padding: 14px 8px;"><span class="badge badge-encrypted">Encrypted</span></td>
                  </tr>
                `;
              }
              const val = r.data || {};
              const dateStr = val.record_date ? new Date(val.record_date).toLocaleDateString('en-GB') : '—';
              const nextDose = val.data && val.data.next_dose ? new Date(val.data.next_dose).toLocaleDateString('en-GB') : '—';
              return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 13px; cursor: pointer;" onclick="window.openRecord(${r.block_index})">
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
};

window.loadMedications = async function() {
  const container = document.getElementById('active-medications-list');
  if (!container) return;
  container.innerHTML = '<div class="loading-spinner">Loading Active Medications...</div>';
  try {
    const pid = patientId();
    const d = await apiFetch(`/api/records/${pid}`);
    const prescriptions = d.records.filter(r => r.record_type === 'prescription' || (r.is_protected && r.title === 'ENCRYPTED VIP RECORD'));
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
        instructions: val.data.notes || '—',
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
                <div class="stat-card glass" style="border-left:3px solid var(--gold); cursor:pointer" onclick="window.openRecord(${m.block_index})">
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
};

window.loadUsers = async function() {
  const container = document.getElementById('users-list');
  if (!container) return;
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
};

window.loadAuditLog = async function() {
  const container = document.getElementById('audit-list');
  if (!container) return;
  container.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const pid = patientId();
    const d = await apiFetch(`/api/blockchain/${pid}/audit?limit=100`);
    if (!d.logs || d.logs.length === 0) {
      container.innerHTML = emptyState('No audit records yet');
      return;
    }
    container.innerHTML = d.logs.map(log => {
      const isAlert = log.action.includes('FAILED') || log.action.includes('REVOKE') || log.action.includes('BREAK_GLASS');
      const statusLabel = isAlert ? 'ALERT' : 'OK';
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
};

window.currentLogTab = 'audit';

window.switchLogTab = function(tab) {
  window.currentLogTab = tab;
  const auditList  = document.getElementById('audit-list');
  const accessList = document.getElementById('access-log-list');
  const btnAudit   = document.getElementById('btn-audit-tab');
  const btnAccess  = document.getElementById('btn-access-tab');

  if (!auditList || !accessList) return;

  if (tab === 'audit') {
    auditList.style.display  = 'block';
    accessList.style.display = 'none';
    if (btnAudit) btnAudit.className = 'btn btn-gold btn-sm';
    if (btnAccess) btnAccess.className = 'btn btn-ghost btn-sm';
    window.loadAuditLog();
  } else {
    auditList.style.display  = 'none';
    accessList.style.display = 'block';
    if (btnAudit) btnAudit.className = 'btn btn-ghost btn-sm';
    if (btnAccess) btnAccess.className = 'btn btn-gold btn-sm';
    window.loadAccessLogs();
  }
};

window.loadAccessLogs = async function() {
  const container = document.getElementById('access-log-list');
  if (!container) return;
  container.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const pid = patientId();
    const d = await apiFetch(`/api/blockchain/${pid}/access-logs?limit=100`);
    if (!d.logs || d.logs.length === 0) {
      container.innerHTML = emptyState('No access log entries yet');
      return;
    }
    container.innerHTML = d.logs.map(log => {
      const isAlert = log.action.includes('FAILED') || log.action.includes('REVOKE') || log.action.includes('BREAK_GLASS');
      const statusLabel = isAlert ? 'ALERT' : 'ACCESS';
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
};

window.refreshLogPage = function() {
  if (window.currentLogTab === 'audit') window.loadAuditLog();
  else window.loadAccessLogs();
};

/* -- Wearable Sync Telemetry ----------------------------------------- */
window.activeWearableData = null;
window.activeWearableSource = '';

window.connectWearable = function(platform) {
  const title = 'Connect Wearable Hub';
  const w = 480, h = 540;
  const left = (window.screen.width/2)-(w/2);
  const top = (window.screen.height/2)-(h/2);
  
  const mockTelemetry = {
    fitbit: { hr: '72', temp: '36.8', spo2: '98', bp: '118/79', source: 'Fitbit Sense 2' },
    google: { hr: '68', temp: '36.5', spo2: '99', bp: '120/80', source: 'Google Pixel Watch' },
    apple: { hr: '70', temp: '36.6', spo2: '97', bp: '115/75', source: 'Apple Watch Ultra' }
  };
  
  window.onOAuthCallback = function(p) {
    if (p !== platform) return;
    window.activeWearableSource = mockTelemetry[platform].source;
    window.activeWearableData = mockTelemetry[platform];
    
    document.getElementById('wearables-preview-empty').style.display = 'none';
    document.getElementById('wearables-preview-data').style.display = 'block';
    document.getElementById('btn-sync-blockchain').style.display = 'block';
    
    document.getElementById('wearable-hr').textContent = window.activeWearableData.hr + ' bpm';
    document.getElementById('wearable-temp').textContent = window.activeWearableData.temp + ' °C';
    document.getElementById('wearable-spo2').textContent = window.activeWearableData.spo2 + ' %';
    document.getElementById('wearable-bp').textContent = window.activeWearableData.bp + ' mmHg';
    document.getElementById('wearable-source-name').textContent = window.activeWearableSource;
    document.getElementById('wearable-timestamp').textContent = new Date().toLocaleTimeString('en-US') + ' ' + new Date().toLocaleDateString('en-GB');
    
    addNotification('Sensor Connected', `Successfully connected to ${window.activeWearableSource}. Data preview loaded.`, 'success');
  };
  
  const popup = window.open('', title, `width=${w},height=${h},top=${top},left=${left}`);
  if (!popup) {
    window.showOAuthModalFallback(platform, mockTelemetry[platform]);
    return;
  }
  
  popup.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>OAuth Connection Hub</title>
      <style>
        body { background: #07070F; color: #EDE8E0; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; padding: 20px; }
        .card { background: #12122A; border: 1px solid rgba(201,168,76,0.25); border-radius: 12px; padding: 30px; text-align: center; max-width: 380px; box-shadow: 0 8px 30px rgba(0,0,0,0.5); }
        .btn { background: linear-gradient(135deg, #C9A84C, #8B6914); color: #000; border: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-top: 20px; width: 100%; transition: opacity 0.2s; }
        .btn:hover { opacity: 0.9; }
        .logo { font-size: 48px; margin-bottom: 15px; }
        h2 { color: #C9A84C; margin-top: 0; }
        p { color: #6B6882; font-size: 14px; line-height: 1.5; }
      </style>
    </head>
    <body>
      <div class="card">
        <div class="logo">⌚</div>
        <h2>Connect ${platform.toUpperCase()}</h2>
        <p>VIP Health Vault requests permission to access your medical telemetry stream (Heart Rate, Temperature, SpO2, and Blood Pressure).</p>
        <button class="btn" onclick="authorize()">AUTHORIZE SYNC</button>
      </div>
      <script>
        function authorize() {
          if (window.opener && !window.opener.closed) {
            window.opener.onOAuthCallback('${platform}');
          }
          window.close();
        }
      <\/script>
    </body>
    </html>
  `);
  popup.document.close();
};

window.showOAuthModalFallback = function(platform, telemetry) {
  document.getElementById('modal-content').innerHTML = `
    <div style="text-align: center; padding: 20px;">
      <div style="font-size: 48px; margin-bottom: 16px;">⌚</div>
      <h2 style="color: var(--gold); font-size: 20px; margin-bottom: 12px;">Connect ${platform.toUpperCase()}</h2>
      <p style="color: var(--muted); font-size: 14px; line-height: 1.5; margin-bottom: 24px;">
        VIP Health Vault requests permission to access your medical telemetry stream (Heart Rate, Temperature, SpO2, and Blood Pressure).
      </p>
      <button class="btn btn-gold btn-full" onclick="window.authorizeFallback('${platform}')">AUTHORIZE SYNC</button>
    </div>
  `;
  document.getElementById('modal-overlay').classList.add('open');
  
  window.authorizeFallback = function(p) {
    closeModal();
    window.onOAuthCallback(p);
  };
};

window.commitWearablesToBlockchain = async function() {
  if (!window.activeWearableData) return;
  const btn = document.getElementById('btn-sync-blockchain');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Syncing...';
  }
  
  const payload = {
    patient_id: patientId(),
    record_type: 'vital_signs',
    title: `Wearables Sensor Telemetry (${window.activeWearableSource})`,
    doctor_name: 'Device Sensor Auto-Sync',
    institution: 'Connected Vitals Core',
    record_date: new Date().toISOString().split('T')[0],
    access_level: 'private',
    is_confidential: false,
    data: {
      heart_rate: window.activeWearableData.hr,
      temperature: window.activeWearableData.temp,
      oxygen_sat: window.activeWearableData.spo2,
      blood_pressure: window.activeWearableData.bp
    },
    notes: `Cryptographically verified vital block synchronization from health wearables via OAuth Gateway.`
  };
  
  try {
    const res = await apiFetch('/api/records', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    addNotification('Sensor Vitals Synced', `Wearable sensor stream successfully verified and committed to block #${res.block_index}.`, 'success');
    window.loadWearables();
    loadDashboard();
  } catch(ex) {
    alert("Blockchain sync failed: " + ex.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'COMMIT TELEMETRY TO BLOCKCHAIN';
    }
  }
};

window.loadWearables = function() {
  window.activeWearableData = null;
  window.activeWearableSource = '';
  const emptyEl = document.getElementById('wearables-preview-empty');
  if (emptyEl) emptyEl.style.display = 'block';
  const dataEl = document.getElementById('wearables-preview-data');
  if (dataEl) dataEl.style.display = 'none';
  const syncBtn = document.getElementById('btn-sync-blockchain');
  if (syncBtn) syncBtn.style.display = 'none';
};

/* -- FHIR Bundle Exporter -------------------------------------------- */
window.exportFHIRBundle = async function() {
  const pid = patientId();
  try {
    const res = await apiFetch(`/api/enabiz/fhir/export/${pid}`);
    const jsonStr = JSON.stringify(res, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fhir_patient_bundle_${pid}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    addNotification('FHIR Bundle Exported', `Official HL7 FHIR Bundle downloaded for patient ${pid}.`, 'success');
  } catch(ex) {
    alert("Failed to export FHIR bundle: " + ex.message);
  }
};

/* -- Environment check (Demo mode and credentials config) ------------ */
async function checkEnvironment() {
  try {
    const config = await apiFetch('/api/config');
    const demoCreds = document.querySelector('.demo-credentials');
    if (demoCreds) {
      if (config.demo_mode) {
        demoCreds.style.display = 'block';
        const demoList = document.getElementById('demo-credentials-list');
        if (demoList && config.demo_accounts) {
          demoList.innerHTML = config.demo_accounts.map(acc => `
            <div class="demo-item" onclick="window.fillCreds('${acc.username}','${acc.password}')">
              <span class="role-badge badge-${acc.role.toLowerCase()}">${acc.role}</span>
              <span>${acc.username} / ${acc.password}</span>
            </div>
          `).join('');
        }
      } else {
        demoCreds.style.display = 'none';
      }
    }
  } catch(e) {
    console.error("Failed to load system config:", e);
  }
}

/* -- Bind Window Properties for Inline Handlers -------------------- */
window.navigate = navigate;
window.logout = logout;
window.resetLoginForm = resetLoginForm;
window.fillCreds = fillCreds;
window.loginWithWeb3Wallet = loginWithWeb3Wallet;
window.loginWithPasskey = loginWithPasskey;
window.registerPasskey = registerPasskey;
window.filterRecords = filterRecords;
window.openRecord = openRecord;
window.decryptRecord = decryptRecord;
window.closeModal = closeModal;
window.renderDynamicFields = renderDynamicFields;
window.loadChainStatus = loadChainStatus;
window.enable2FA = enable2FA;
window.disable2FA = disable2FA;
window.setup2FA = setup2FA;
window.sendTriageSymptom = sendTriageSymptom;
window.showBookAppointmentModal = showBookAppointmentModal;
window.bookAppointment = bookAppointment;
window.cancelAppointment = cancelAppointment;
window.toggleNotifications = toggleNotifications;
window.clearAllNotifications = clearAllNotifications;
window.markAsRead = markAsRead;
window.markAllAsRead = markAllAsRead;
window.grantConsent = grantConsent;
window.revokeConsent = revokeConsent;
window.triggerBreakGlass = triggerBreakGlass;
window.loadConsents = loadConsents;
window.loadRecords = loadRecords;
window.loadDashboard = loadDashboard;
window.renderRecordCard = renderRecordCard;

// DICOM Viewer Functions
window.zoomDicom = zoomDicom;
window.invertDicom = invertDicom;
window.resetDicom = resetDicom;
window.downloadBase64File = downloadBase64File;
window.downloadOffchainFile = downloadOffchainFile;
window.startAddingDicomAnnotation = startAddingDicomAnnotation;
window.deleteDicomAnnotation = deleteDicomAnnotation;
window.setDicomLevel = setDicomLevel;
window.setDicomWidth = setDicomWidth;

/* ── COMMAND PALETTE LOGIC ───────────────────────────────── */
let commandPaletteSelectedIdx = 0;
let commandPaletteVisibleResults = [];

window.openCommandPalette = async function() {
  const pal = document.getElementById('command-palette');
  if (!pal) return;
  pal.classList.add('open');
  const inp = document.getElementById('command-palette-input');
  if (inp) {
    inp.value = '';
    inp.focus();
  }
  commandPaletteSelectedIdx = 0;
  renderCommandPaletteResults('');

  // Fetch records if empty to ensure search is populated
  if (!allRecords || allRecords.length === 0) {
    try {
      await loadRecords();
      renderCommandPaletteResults(inp ? inp.value : '');
    } catch (e) {
      console.error("Failed to pre-fetch records for command palette:", e);
    }
  }
};

window.closeCommandPalette = function() {
  const pal = document.getElementById('command-palette');
  if (!pal) return;
  pal.classList.remove('open');
};

function renderCommandPaletteResults(query = '') {
  const resultsContainer = document.getElementById('command-palette-results');
  if (!resultsContainer) return;
  
  query = query.trim().toLowerCase();
  
  const pages = [
    { type: 'nav', page: 'dashboard', title: 'Dashboard Overview', desc: 'System status, recent records, and vitals', shortcut: 'G D' },
    { type: 'nav', page: 'records', title: 'Medical Records', desc: 'Browse and decrypt blockchain health blocks', shortcut: 'G R' },
    { type: 'nav', page: 'add-record', title: 'Add Health Record', desc: 'Commit clinical observations and files to chain', shortcut: 'G N' },
    { type: 'nav', page: 'chain-status', title: 'Chain Status Verification', desc: 'Verify cryptographic block structures', shortcut: 'G C' },
    { type: 'nav', page: 'vaccines', title: 'Vaccine Passport', desc: 'Immutably registry for vaccines', shortcut: 'G V' },
    { type: 'nav', page: 'medications', title: 'Medications & Prescriptions', desc: 'Active prescriptions and dosage instructions', shortcut: 'G M' },
    { type: 'nav', page: 'consent', title: 'Consent Settings', desc: 'Doctor permissions and Break Glass', shortcut: 'G S' },
    { type: 'nav', page: 'security', title: 'Security & 2FA', desc: 'Manage Multi-Factor Authentication', shortcut: 'G A' },
    { type: 'nav', page: 'wearables', title: 'Wearables Integration Hub', desc: 'Sync telemetry stream directly to blockchain', shortcut: 'G W' },
    { type: 'nav', page: 'appointments', title: 'Clinic Appointments', desc: 'Schedule consultations with clinical specialists', shortcut: 'G P' },
    { type: 'nav', page: 'triage', title: 'AI Symptom Triage', desc: 'AI symptom risk scoring and prioritisation', shortcut: 'G T' }
  ];

  const currentUser = getCurrentUser();
  if (currentUser && currentUser.role === 'admin') {
    pages.push(
      { type: 'nav', page: 'audit', title: 'Access & Audit History', desc: 'Comprehensive audit logs for all access (Admin)', shortcut: 'G L' },
      { type: 'nav', page: 'users', title: 'User Management', desc: 'Configure system roles and patient mappings (Admin)', shortcut: 'G U' }
    );
  }

  const actions = [
    { type: 'action', action: 'logout', title: 'Sign Out / Logout', desc: 'Terminate session and clear token', shortcut: '⌥ L' },
    { type: 'action', action: 'export', title: 'Export HL7 FHIR Bundle', desc: 'Download official HL7 FHIR Bundle', shortcut: '⌥ E' },
    { type: 'action', action: 'refresh_chain', title: 'Refresh Chain Status', desc: 'Query and update cryptographic statuses', shortcut: '⌥ R' }
  ];

  if (currentUser && currentUser.role === 'doctor') {
    actions.push({ type: 'action', action: 'break_glass', title: 'Trigger Break Glass (Emergency)', desc: 'Emergency override access to patient data', shortcut: '⌥ B' });
  }

  let filteredItems = [];

  const allCommands = [...pages, ...actions];
  const matchedCommands = allCommands.filter(item => 
    item.title.toLowerCase().includes(query) || 
    item.desc.toLowerCase().includes(query)
  );
  
  if (matchedCommands.length > 0) {
    filteredItems.push({
      group: 'Commands & Navigation',
      items: matchedCommands
    });
  }

  if (allRecords && allRecords.length > 0) {
    const matchedRecords = allRecords.filter(r => {
      const d = r.data || {};
      const txt = (r.title + ' ' + (d.doctor_name||'') + ' ' + (d.institution||'') + ' ' + (r.record_type||'')).toLowerCase();
      return txt.includes(query);
    }).map(r => ({
      type: 'record',
      block_index: r.block_index,
      title: r.title,
      desc: `Block #${r.block_index} · ${(r.data?.doctor_name || 'System')} · ${r.data?.record_date || 'Date N/A'}`,
      shortcut: `#${r.block_index}`
    }));

    if (matchedRecords.length > 0) {
      filteredItems.push({
        group: 'Medical Records',
        items: query ? matchedRecords : matchedRecords.slice(0, 5)
      });
    }
  }

  commandPaletteVisibleResults = [];
  filteredItems.forEach(group => {
    group.items.forEach(item => {
      commandPaletteVisibleResults.push(item);
    });
  });

  if (commandPaletteVisibleResults.length === 0) {
    resultsContainer.innerHTML = `<div style="padding: 16px; text-align: center; color: var(--muted); font-size: 13px;">No results found for "${query}"</div>`;
    return;
  }

  let html = '';
  let globalIndex = 0;
  filteredItems.forEach(group => {
    html += `<div class="command-palette-group-title">${group.group}</div>`;
    group.items.forEach(item => {
      const isSelected = globalIndex === commandPaletteSelectedIdx;
      html += `
        <div class="command-palette-item ${isSelected ? 'selected' : ''}" data-index="${globalIndex}" onclick="triggerCommandPaletteItem(${globalIndex})">
          <div class="command-palette-item-icon">
            ${item.type === 'nav' ? '🧭' : item.type === 'action' ? '⚡' : '📄'}
          </div>
          <div class="command-palette-item-content">
            <div class="command-palette-item-title">${item.title}</div>
            <div class="command-palette-item-desc">${item.desc}</div>
          </div>
          ${item.shortcut ? `<span class="command-palette-item-shortcut">${item.shortcut}</span>` : ''}
        </div>
      `;
      globalIndex++;
    });
  });

  resultsContainer.innerHTML = html;
  
  const selectedEl = resultsContainer.querySelector('.command-palette-item.selected');
  if (selectedEl) {
    selectedEl.scrollIntoView({ block: 'nearest' });
  }
}

window.triggerCommandPaletteItem = function(index) {
  const item = commandPaletteVisibleResults[index];
  if (!item) return;
  
  window.closeCommandPalette();
  
  if (item.type === 'nav') {
    navigate(item.page);
  } else if (item.type === 'action') {
    if (item.action === 'logout') {
      logout();
    } else if (item.action === 'export') {
      exportFHIRBundle();
    } else if (item.action === 'refresh_chain') {
      loadChainStatus();
    } else if (item.action === 'break_glass') {
      navigate('consent');
      setTimeout(() => {
        const bgPanel = document.getElementById('break-glass-panel');
        if (bgPanel) {
          bgPanel.scrollIntoView({ behavior: 'smooth' });
          const text = document.getElementById('break-glass-reason');
          if (text) text.focus();
        }
      }, 300);
    }
  } else if (item.type === 'record') {
    window.openRecord(item.block_index);
  }
};

function initCommandPaletteListeners() {
  const inp = document.getElementById('command-palette-input');
  if (!inp) return;
  
  inp.addEventListener('input', (e) => {
    commandPaletteSelectedIdx = 0;
    renderCommandPaletteResults(e.target.value);
  });
  
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (commandPaletteVisibleResults.length > 0) {
        commandPaletteSelectedIdx = (commandPaletteSelectedIdx + 1) % commandPaletteVisibleResults.length;
        renderCommandPaletteResults(inp.value);
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (commandPaletteVisibleResults.length > 0) {
        commandPaletteSelectedIdx = (commandPaletteSelectedIdx - 1 + commandPaletteVisibleResults.length) % commandPaletteVisibleResults.length;
        renderCommandPaletteResults(inp.value);
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (commandPaletteVisibleResults.length > 0) {
        window.triggerCommandPaletteItem(commandPaletteSelectedIdx);
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      window.closeCommandPalette();
    }
  });
}

// Global hotkey cmd+k / ctrl+k listener
window.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    const pal = document.getElementById('command-palette');
    if (pal && pal.classList.contains('open')) {
      window.closeCommandPalette();
    } else {
      window.openCommandPalette();
    }
  }
});


/* ── BLOCKCHAIN EXPLORER LOGIC ───────────────────────────── */
window.toggleBlockchainExplorer = async function() {
  const sidebar = document.getElementById('blockchain-explorer-sidebar');
  if (!sidebar) return;
  
  const isOpen = sidebar.classList.toggle('open');
  if (isOpen) {
    await window.loadBlockchainExplorerData();
  }
};

window.loadBlockchainExplorerData = async function() {
  const listContainer = document.getElementById('explorer-blocks-list');
  const statusText = document.getElementById('explorer-status-text');
  const dot = document.getElementById('explorer-chain-dot');
  
  if (!listContainer) return;
  listContainer.innerHTML = '<div class="loading-spinner">Loading blocks...</div>';
  
  try {
    const pid = patientId();
    if (!pid) {
      listContainer.innerHTML = '<div class="alert alert-error">No active patient ID found.</div>';
      return;
    }
    
    const [status, records] = await Promise.all([
      apiFetch(`/api/blockchain/${pid}/status`),
      apiFetch(`/api/records/${pid}`)
    ]);
    
    const valid = status.is_valid;
    const onChainVerified = status.on_chain_verified;
    const isSimulated = status.is_simulated;
    const onChainPill = onChainVerified 
      ? (isSimulated 
          ? `<span class="badge badge-private" style="background:rgba(245,158,11,0.1);color:#F59E0B;border:1px solid rgba(245,158,11,0.3);cursor:pointer;font-size:9px;padding:2px 6px;" onclick="navigator.clipboard.writeText('${status.on_chain_tx_hash}'); alert('Copied Simulated Tx Hash: ' + '${status.on_chain_tx_hash}');" title="Click to copy Simulated Tx Hash">Simulated Anchor</span>`
          : `<span class="badge badge-shared" style="background:rgba(16,185,129,0.1);color:#10b981;border:1px solid rgba(16,185,129,0.3);cursor:pointer;font-size:9px;padding:2px 6px;" onclick="navigator.clipboard.writeText('${status.on_chain_tx_hash}'); alert('Copied Anchor Tx Hash: ' + '${status.on_chain_tx_hash}');" title="Click to copy Anchor Tx Hash">On-Chain Verified</span>`
        )
      : `<span class="badge badge-private" style="background:rgba(239,68,68,0.1);color:#ef4444;border:1px solid rgba(239,68,68,0.3);font-size:9px;padding:2px 6px;">Not Anchored</span>`;

    const statusBox = document.querySelector('.explorer-sidebar-status');
    if (statusBox) {
      statusBox.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; width:100%;">
          <div class="explorer-status-pill" style="display:flex; align-items:center; gap:8px;">
            <span class="chain-dot ${valid ? 'valid' : 'invalid'}"></span>
            <span id="explorer-status-text" style="color:${valid ? 'var(--success)' : 'var(--danger)'}; font-size:11px;">
              ${valid ? `Chain Secured (${status.chain_length} Blocks)` : `CHAIN CORRUPTED`}
            </span>
          </div>
          ${onChainPill}
        </div>
      `;
    }
    
    const blocks = records.records || [];
    if (blocks.length === 0) {
      listContainer.innerHTML = '<div class="empty-state"><p>No blocks found in this patient chain.</p></div>';
      return;
    }
    
    // Display in reverse order (newest blocks first)
    const sortedBlocks = [...blocks].reverse();
    
    listContainer.innerHTML = sortedBlocks.map(b => {
      const isGenesis = b.block_index === 0;
      const isAudit = b.record_type === 'audit' || b.title?.includes('AUDIT') || b.title?.includes('ACCESS');
      const typeLabel = isGenesis ? 'Genesis' : (isAudit ? 'Audit' : 'Data');
      const typeClass = isGenesis ? 'genesis' : (isAudit ? 'audit' : 'data');
      const broken = status.broken_at !== null && b.block_index >= status.broken_at;
      
      return `
        <div class="explorer-block-card ${broken ? 'broken-block' : `${typeClass}-block`}">
          <div class="explorer-blk-title">
            <span>BLOCK #${b.block_index}</span>
            <span class="explorer-blk-type explorer-type-${typeClass}">${typeLabel}</span>
          </div>
          <div class="explorer-blk-row">
            <span class="explorer-blk-lbl">Title:</span>
            <span class="explorer-blk-val" style="font-weight:600">${b.title || '—'}</span>
          </div>
          <div class="explorer-blk-row">
            <span class="explorer-blk-lbl">Timestamp:</span>
            <span class="explorer-blk-val">${formatTs(b.timestamp)}</span>
          </div>
          <div class="explorer-blk-row">
            <span class="explorer-blk-lbl">Hash:</span>
            <span class="explorer-blk-val hash">${b.hash_preview || '—'}</span>
          </div>
          <div class="explorer-blk-row">
            <span class="explorer-blk-lbl">Prev Hash:</span>
            <span class="explorer-blk-val">${b.prev_hash_preview || '—'}</span>
          </div>
          <div class="explorer-blk-row">
            <span class="explorer-blk-lbl">Merkle Root:</span>
            <span class="explorer-blk-val">${b.merkle_root_preview || '—'}</span>
          </div>
          <div class="explorer-blk-row">
            <span class="explorer-blk-lbl">Signature:</span>
            <span class="explorer-blk-val">${b.signature_preview || '—'}</span>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    listContainer.innerHTML = `<div class="alert alert-error">Error loading explorer: ${err.message}</div>`;
  }
};

/* ── THEME SWITCHER LOGIC ─────────────────────────────────── */
window.switchTheme = function(themeName) {
  document.body.classList.remove('theme-slate', 'theme-emerald', 'theme-steel');
  if (themeName && themeName !== 'default') {
    document.body.classList.add(`theme-${themeName}`);
  }
  localStorage.setItem('vhv_theme', themeName || 'default');
  const sel = document.getElementById('theme-selector');
  if (sel) sel.value = themeName || 'default';
};

(function initTheme() {
  const savedTheme = localStorage.getItem('vhv_theme') || 'default';
  window.switchTheme(savedTheme);
})();

// Auto-run on load
const token = localStorage.getItem('vhv_token');
const currentUser = getCurrentUser();

initAuthListeners();
initRecordsListeners();
initCommandPaletteListeners();

// Bind QR Emergency Access to window
window.showEmergencyQR   = showEmergencyQR;
window.revokeEmergencyQR = revokeEmergencyQR;
window.closeEmergencyQR  = closeEmergencyQR;

// Bind Dead-Man's Switch to window
window.showDeadManModal  = showDeadManModal;
window.sendDeadManPing   = sendDeadManPing;
window.saveDeadManConfig = saveDeadManConfig;
window.closeDeadManModal = closeDeadManModal;

if (token && currentUser) {
  window.enterApp();
  // Show emergency QR & Dead-Man trigger buttons for VIP patients
  if (currentUser.role === 'vip_patient') {
    const qrTrigger = document.getElementById('emergency-qr-trigger');
    if (qrTrigger) qrTrigger.style.display = 'block';

    const dmTrigger = document.getElementById('deadman-trigger');
    if (dmTrigger) dmTrigger.style.display = 'block';
  }
} else {
  resetLoginFormState();
}

checkEnvironment();
