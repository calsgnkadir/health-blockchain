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
      <div style="overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; text-align: left; color: #fff;">
          <thead>
            <tr style="border-bottom: 1px solid var(--border); color: var(--muted-hi); font-size: 13px;">
              <th style="padding: 10px 8px;">Doctor</th>
              <th style="padding: 10px 8px;">Record Type</th>
              <th style="padding: 10px 8px;">Expires At</th>
              <th style="padding: 10px 8px; text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody>
            ${consents.map(c => {
              const expDate = new Date(c.expiry_timestamp * 1000).toLocaleDateString('en-GB');
              return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 13px;">
                  <td style="padding: 12px 8px; font-weight: 600;">Dr. ${c.doctor_username}</td>
                  <td style="padding: 12px 8px;"><span class="badge badge-shared">${typeLabels[c.record_type] || c.record_type}</span></td>
                  <td style="padding: 12px 8px;">${expDate}</td>
                  <td style="padding: 12px 8px; text-align: right;">
                    <button class="btn btn-error btn-sm" style="padding: 4px 10px; font-size: 11px;" onclick="window.revokeConsent('${c.doctor_username}', '${c.record_type}')">Revoke</button>
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
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
