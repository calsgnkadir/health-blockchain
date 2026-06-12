/* consent.js — VIP Health Vault UI Consent Management Module */
import { apiFetch, patientId } from './utils.js';
import { addNotification } from './notifications.js';

export async function loadConsents() {
  const container = document.getElementById('consents-list');
  if (!container) return;
  container.innerHTML = '<div class="loading-spinner">Loading consent rules...</div>';

  try {
    const pid = patientId();
    const res = await apiFetch(`/api/consent/${pid}`);
    const consents = res.consents || [];

    if (consents.length === 0) {
      container.innerHTML = `<div class="empty-state"><p>No active consent permissions granted for your healthcare providers.</p></div>`;
      return;
    }

    const typeLabels = {
      all: 'All Records',
      diagnosis: 'Diagnosis',
      lab_result: 'Lab Result',
      prescription: 'Prescription',
      imaging: 'Imaging (MRI/CT/X-Ray)',
      vital_signs: 'Vital Signs',
      other: 'Other'
    };

    container.innerHTML = `
      <div class="consent-gantt-chart">
        ${consents.map(c => {
          const expDate = new Date(c.expiry_timestamp * 1000).toLocaleDateString('en-GB');
          const grantedVal = c.granted_at || (c.expiry_timestamp - 30 * 86400);
          const grantedDate = new Date(grantedVal * 1000).toLocaleDateString('en-GB');
          
          const now = Date.now() / 1000;
          const totalDuration = c.expiry_timestamp - grantedVal;
          const elapsed = now - grantedVal;
          const pct = Math.max(0, Math.min(100, 100 - (elapsed / (totalDuration || 1)) * 100));
          
          return `
            <div class="gantt-row">
              <div class="gantt-label">
                <div style="font-weight:700;color:#fff;">Dr. ${c.doctor_username}</div>
                <div style="font-size:10px;color:var(--accent-ledger);font-weight:600;text-transform:uppercase;">${typeLabels[c.record_type] || c.record_type}</div>
              </div>
              <div style="display:flex;flex-direction:column;gap:6px;">
                <div class="gantt-timeline-track">
                  <div class="gantt-bar" style="width: ${pct}%"></div>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;color:var(--muted)">
                  <span>Granted: ${grantedDate}</span>
                  <span>Expires: ${expDate}</span>
                  <button class="btn btn-error btn-sm" style="padding:2px 8px;font-size:10px;border-radius:4px;font-weight:600;" onclick="window.revokeConsent('${c.doctor_username}', '${c.record_type}')">Revoke</button>
                </div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  } catch (e) {
    container.innerHTML = `<div class="alert alert-error">Failed to load consents: ${e.message}</div>`;
  }
}

export async function grantConsent(event) {
  if (event) event.preventDefault();
  const errEl = document.getElementById('consent-error');
  const succEl = document.getElementById('consent-success');
  if (errEl) errEl.style.display = 'none';
  if (succEl) succEl.style.display = 'none';

  const doctor = document.getElementById('consent-doctor').value.trim();
  const recordType = document.getElementById('consent-record-type').value;
  const duration = parseInt(document.getElementById('consent-duration').value || 30);

  if (!doctor) {
    if (errEl) {
      errEl.textContent = 'Doctor username is required.';
      errEl.style.display = 'block';
    }
    return;
  }

  try {
    const pid = patientId();
    await apiFetch('/api/consent', {
      method: 'POST',
      body: JSON.stringify({
        patient_id: pid,
        doctor_username: doctor,
        record_type: recordType,
        duration_days: duration
      })
    });

    if (succEl) {
      succEl.textContent = `Consent successfully granted to Dr. ${doctor} for ${recordType} records.`;
      succEl.style.display = 'block';
    }

    addNotification('Consent Granted', `Granted access to Dr. ${doctor} for ${recordType} records.`, 'success');
    document.getElementById('consent-form').reset();
    document.getElementById('consent-duration').value = 30;
    loadConsents();
  } catch (e) {
    if (errEl) {
      errEl.textContent = e.message;
      errEl.style.display = 'block';
    }
  }
}

export async function revokeConsent(doctorUsername, recordType) {
  if (!confirm(`Are you sure you want to revoke Dr. ${doctorUsername}'s access to your ${recordType} records?`)) return;

  try {
    const pid = patientId();
    await apiFetch(`/api/consent/${pid}/${doctorUsername}/${recordType}`, {
      method: 'DELETE'
    });

    addNotification('Consent Revoked', `Revoked Dr. ${doctorUsername}'s access to ${recordType} records.`, 'info');
    loadConsents();
  } catch (e) {
    alert("Failed to revoke consent: " + e.message);
  }
}

export async function triggerBreakGlass(event) {
  if (event) event.preventDefault();
  const errEl = document.getElementById('breakglass-error');
  const succEl = document.getElementById('breakglass-success');
  if (errEl) errEl.style.display = 'none';
  if (succEl) succEl.style.display = 'none';

  const reason = document.getElementById('breakglass-reason').value.trim();
  if (!reason) {
    if (errEl) {
      errEl.textContent = 'Please provide a justification reason for the break-glass override.';
      errEl.style.display = 'block';
    }
    return;
  }

  try {
    const pid = patientId();
    const res = await apiFetch(`/api/consent/${pid}/break-glass`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    });

    if (succEl) {
      succEl.textContent = res.message || 'Emergency bypass executed successfully.';
      succEl.style.display = 'block';
    }

    addNotification('Break-Glass Invoked', `Emergency override executed for patient ${pid}. Reason: ${reason}`, 'warning');
    document.getElementById('break-glass-form').reset();
    
    // Refresh records if the physician is viewing them
    if (window.loadRecords) window.loadRecords();
    if (window.loadDashboard) window.loadDashboard();
  } catch (e) {
    if (errEl) {
      errEl.textContent = e.message;
      errEl.style.display = 'block';
    }
  }
}
