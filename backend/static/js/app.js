import { API, apiFetch, patientId, formatTs, formatTsFull, emptyState, ROLE_LABEL, getCurrentUser, getDualControlToken, setDualControlToken, appState } from './modules/utils.js';
import { mfaRequired, resetLoginFormState, resetLoginForm, fillCreds, handleLoginSubmit, logout, setup2FA, enable2FA, disable2FA, initAuthListeners, loginWithPasskey, registerPasskey } from './modules/auth.js';
import { updateChainPill, updateClinicalHighlights, renderVitalsChart, loadDashboard, navigate } from './modules/dashboard.js';
import { allRecords, recordTypes, loadRecordTypes, loadRecords, filterRecords, renderAllRecords, renderRecordCard, renderAttachmentHtml, downloadBase64File, downloadOffchainFile, openRecord, decryptRecord, closeModal, DYNAMIC_FIELDS, renderDynamicFields, zoomDicom, invertDicom, resetDicom, initRecordsListeners, startAddingDicomAnnotation, deleteDicomAnnotation, setDicomLevel, setDicomWidth } from './modules/records.js';
import { getNotifications, addNotification, updateNotificationsUI, toggleNotifications, closeAllDropdowns, markAsRead, markAllAsRead, clearAllNotifications } from './modules/notifications.js';
import { loadConsents, grantConsent, revokeConsent, triggerBreakGlass } from './modules/consent.js';
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
  if (pageApp) {
    pageApp.style.display = 'flex';
    pageApp.classList.add('active');
  }

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
              const dateStr = r.record_date ? new Date(r.record_date).toLocaleDateString('en-GB') : '—';
              const nextDose = val.next_dose ? new Date(val.next_dose).toLocaleDateString('en-GB') : '—';
              return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 13px; cursor: pointer;" onclick="window.openRecord(${r.block_index})">
                  <td style="padding: 14px 8px; font-weight: 600;">${val.vaccine_name || '—'}</td>
                  <td style="padding: 14px 8px; font-family: var(--font-mono);">${val.lot_number || '—'}</td>
                  <td style="padding: 14px 8px;">Dose ${val.dose_number || '1'}</td>
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
      const recordDate = new Date(r.record_date);
      const durationDays = parseInt(val.duration || 0);
      const expiryDate = new Date(recordDate.getTime() + durationDays * 24 * 60 * 60 * 1000);
      const today = new Date();
      today.setHours(0,0,0,0);
      expiryDate.setHours(0,0,0,0);
      
      const details = {
        block_index: r.block_index,
        title: r.title,
        medication: val.medication || 'Unknown',
        dose: val.dose || '—',
        frequency: val.frequency || '—',
        duration: durationDays,
        instructions: r.notes || '—',
        record_date: r.record_date,
        doctor: r.doctor_name,
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

window.loadDualControl = function() {
  const errEl = document.getElementById('dc-error');
  const succEl = document.getElementById('dc-success');
  if (errEl) errEl.style.display = 'none';
  if (succEl) succEl.style.display = 'none';
  window.renderDualControlToken();
  // Pick up a co-signature granted while this page was closed.
  if (getDualControlToken()) window.refreshDualControlStatus();
};

window.renderDualControlToken = function() {
  const box = document.getElementById('dc-active-token');
  if (!box) return;

  const token = getDualControlToken();
  if (!token) {
    box.innerHTML = `
      <div class="glass" style="padding:16px; border-radius:var(--radius); border:1px solid var(--border);">
        <div style="font-size:13px; color:var(--muted);">No co-signed token held. Patient records stay locked until a second privileged principal approves a request.</div>
      </div>`;
    return;
  }

  const approved = token.status === 'APPROVED';
  const expiresIn = token.expires_at ? Math.max(0, Math.round((token.expires_at * 1000 - Date.now()) / 60000)) : null;
  box.innerHTML = `
    <div class="glass" style="padding:16px 20px; border-radius:var(--radius); border:1px solid ${approved ? 'rgba(16,185,129,0.35)' : 'rgba(245,158,11,0.35)'};">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap;">
        <div>
          <div style="font-weight:700; font-size:14px; color:${approved ? '#10b981' : '#f59e0b'};">
            ${approved ? 'CO-SIGNED — raw record access unlocked' : 'PENDING CO-APPROVAL'}
          </div>
          <div style="font-size:12px; color:var(--muted-hi); margin-top:4px;">
            Patient <strong>${token.target_patient_id || '—'}</strong> ·
            Token <code style="font-family:var(--font-mono);">${token.token_id}</code>
            ${expiresIn !== null ? ` · expires in ${expiresIn} min` : ''}
          </div>
          ${token.co_signed_by ? `<div style="font-size:12px; color:var(--muted); margin-top:2px;">Co-signed by <strong>${token.co_signed_by}</strong></div>` : ''}
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-ghost btn-sm" onclick="window.refreshDualControlStatus()">Refresh Status</button>
          <button class="btn btn-ghost btn-sm" onclick="window.clearDualControlToken()">Discard Token</button>
        </div>
      </div>
    </div>`;
};

window.refreshDualControlStatus = async function() {
  const held = getDualControlToken();
  if (!held) return;
  const errEl = document.getElementById('dc-error');
  try {
    const info = await apiFetch(`/api/security/dual-control/${held.token_id}`);
    setDualControlToken({
      token_id: info.token_id,
      status: info.status,
      target_patient_id: info.target_patient_id,
      expires_at: info.expires_at,
      co_signed_by: info.co_signed_by
    });
    window.renderDualControlToken();
    if (info.status === 'APPROVED') {
      addNotification('Dual-Control Approved', `Token ${info.token_id} was co-signed by ${info.co_signed_by}.`, 'success');
    }
  } catch (e) {
    if (errEl) {
      errEl.textContent = e.message;
      errEl.style.display = 'block';
    }
  }
};

window.clearDualControlToken = function() {
  setDualControlToken(null);
  window.renderDualControlToken();
  addNotification('Dual-Control Token Discarded', 'Privileged raw record access has been relinquished.', 'info');
};

window.requestDualControl = async function(event) {
  if (event) event.preventDefault();
  const errEl = document.getElementById('dc-error');
  const succEl = document.getElementById('dc-success');
  errEl.style.display = 'none';
  succEl.style.display = 'none';

  try {
    const res = await apiFetch('/api/security/dual-control/request', {
      method: 'POST',
      body: JSON.stringify({
        request_type: 'DECRYPT_RAW_RECORD',
        target_patient_id: document.getElementById('dc-patient-id').value.trim(),
        reason: document.getElementById('dc-reason').value.trim(),
        validity_minutes: parseInt(document.getElementById('dc-validity').value || 30)
      })
    });

    setDualControlToken({
      token_id: res.token_id,
      status: res.status,
      target_patient_id: document.getElementById('dc-patient-id').value.trim(),
      expires_at: res.expires_at
    });
    window.renderDualControlToken();

    succEl.textContent = `${res.message} Token: ${res.token_id}`;
    succEl.style.display = 'block';
    document.getElementById('dc-cosign-token').value = res.token_id;
    addNotification('Dual-Control Requested', `Access request raised for ${document.getElementById('dc-patient-id').value.trim()}. Awaiting co-signature.`, 'warning');
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
  }
};

window.coSignDualControl = async function(event) {
  if (event) event.preventDefault();
  const errEl = document.getElementById('dc-error');
  const succEl = document.getElementById('dc-success');
  errEl.style.display = 'none';
  succEl.style.display = 'none';

  const tokenId = document.getElementById('dc-cosign-token').value.trim();
  try {
    const res = await apiFetch('/api/security/dual-control/co-sign', {
      method: 'POST',
      body: JSON.stringify({ token_id: tokenId })
    });

    // Only the requester benefits from holding the token locally; a co-signer
    // approving someone else's request keeps whatever token they already had.
    const held = getDualControlToken();
    if (held && held.token_id === res.token_id) {
      setDualControlToken({ ...held, status: res.status, co_signed_by: res.co_signed_by });
    }
    window.renderDualControlToken();

    succEl.textContent = res.message;
    succEl.style.display = 'block';
    addNotification('Dual-Control Co-Signed', `Token ${res.token_id} approved for patient ${res.target_patient_id}.`, 'success');
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
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
window.handleLoginSubmit = handleLoginSubmit;
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

/* -- Security Settings Page Loader -------------------------------- */
window.loadSecuritySettings = function() {
  const statusBox = document.getElementById('mfa-status-box');
  if (!statusBox) return;

  const currentUser = getCurrentUser();
  if (!currentUser) return;

  const setupSection = document.getElementById('mfa-setup-section');
  const disableSection = document.getElementById('mfa-disable-section');

  if (currentUser.totp_enabled) {
    statusBox.innerHTML = `
      <div style="display:flex; align-items:center; gap:10px; padding:14px; border-radius:8px; background:rgba(16,185,129,0.08); border:1px solid rgba(16,185,129,0.25);">
        <span style="font-size:20px;">✅</span>
        <div>
          <div style="font-weight:700; color:#10b981; font-size:14px;">Two-Factor Authentication is ENABLED</div>
          <div style="font-size:12px; color:var(--muted); margin-top:2px;">Your account is protected with TOTP 2FA.</div>
        </div>
      </div>
    `;
    if (setupSection) setupSection.style.display = 'none';
    if (disableSection) disableSection.style.display = 'block';
  } else {
    statusBox.innerHTML = `
      <div style="display:flex; align-items:center; gap:10px; padding:14px; border-radius:8px; background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.25);">
        <span style="font-size:20px;">⚠️</span>
        <div>
          <div style="font-weight:700; color:#f59e0b; font-size:14px;">Two-Factor Authentication is NOT enabled</div>
          <div style="font-size:12px; color:var(--muted); margin-top:2px;">Enable 2FA to secure your VIP Health Vault account.</div>
        </div>
      </div>
      <button class="btn btn-gold" style="margin-top:16px;" onclick="window.setup2FA()">Setup 2FA Now</button>
    `;
    if (setupSection) setupSection.style.display = 'none';
    if (disableSection) disableSection.style.display = 'none';
  }

  // Clear any previous error/success messages
  const errEl = document.getElementById('security-error');
  const succEl = document.getElementById('security-success');
  if (errEl) errEl.style.display = 'none';
  if (succEl) succEl.style.display = 'none';

  // Set saved theme on selector
  const savedTheme = localStorage.getItem('vhv_theme') || 'default';
  const sel = document.getElementById('theme-selector');
  if (sel) sel.value = savedTheme;
};

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
    { type: 'nav', page: 'security', title: 'Security & 2FA', desc: 'Manage Multi-Factor Authentication', shortcut: 'G A' }
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
      const txt = ((r.title||'') + ' ' + (r.doctor_name||'') + ' ' + (r.institution||'') + ' ' + (r.record_type||'')).toLowerCase();
      return txt.includes(query);
    }).map(r => ({
      type: 'record',
      block_index: r.block_index,
      title: r.title,
      desc: `Block #${r.block_index} · ${(r.doctor_name || 'System')} · ${r.record_date || 'Date N/A'}`,
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

if (token && currentUser) {
  window.enterApp();
} else {
  resetLoginFormState();
}

checkEnvironment();
