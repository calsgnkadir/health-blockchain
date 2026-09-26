/* clients.js — client invitations
 *
 * Practitioner side ("My Clients"): invite a new client by name, get a one-time
 * invitation code, and see which invited clients have joined.
 *
 * Client side (login screen): redeem the code and choose a password.
 *
 * An invitation never gives the practitioner access to the client's records;
 * the client grants consent themselves after signing in.
 */
import { apiFetch, escapeHtml, emptyState, formatTs, setSelectedPatient } from './utils.js';
import { navigate } from './dashboard.js';

const STATUS = {
  pending: { label: 'Waiting for client', cls: 'badge-private' },
  active:  { label: 'Joined',             cls: 'badge-shared' },
  expired: { label: 'Code expired',       cls: 'badge-encrypted' },
};

// The code travels in the URL fragment (#invite=...). Browsers never send the
// fragment to the server, so the code does not end up in access logs.
function inviteLink(code) {
  return `${location.origin}/#invite=${encodeURIComponent(code)}`;
}

function showError(id, message) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = message;
  el.style.display = message ? 'block' : 'none';
}

/* -- Practitioner: My Clients ---------------------------------------- */

export async function loadClients() {
  loadStaff();
  const list = document.getElementById('clients-list');
  if (!list) return;
  list.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const d = await apiFetch('/api/onboarding/invitations');
    if (!d.invitations.length) {
      list.innerHTML = emptyState('No clients yet. Invite your first client above.');
      return;
    }
    list.innerHTML = d.invitations.map(renderInvitation).join('');
  } catch (e) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
  }
}

function renderInvitation(inv) {
  const st = STATUS[inv.status] || { label: inv.status, cls: '' };
  const pid = escapeHtml(inv.patient_id);
  const button = inv.status === 'active'
    ? `<button type="button" class="btn btn-ghost btn-sm" data-action="open-client" data-arg="${pid}">Open file</button>`
    : `<button type="button" class="btn btn-ghost btn-sm" data-action="renew-invite" data-arg="${pid}">New code</button>`;
  return `
    <div class="user-card glass">
      <div class="user-avatar" style="background:linear-gradient(135deg,#C9A84C,#8B6914)">${escapeHtml(inv.full_name.charAt(0))}</div>
      <div style="flex:1">
        <div style="font-weight:600">${escapeHtml(inv.full_name)}</div>
        <div style="font-size:12px;color:var(--muted)">${pid} · invited ${escapeHtml(formatTs(inv.invited_at))}</div>
      </div>
      <span class="badge ${st.cls}">${escapeHtml(st.label)}</span>
      ${button}
    </div>`;
}

function showInviteResult(d) {
  document.getElementById('invite-result').hidden = false;
  document.getElementById('invite-result-id').textContent = d.patient_id;
  document.getElementById('invite-result-username').textContent = d.username;
  document.getElementById('invite-result-expiry').textContent =
    new Date(d.expires_at * 1000).toLocaleString('en-GB');
  document.getElementById('invite-result-code').value = d.invite_code;
  document.getElementById('invite-result-link').value = inviteLink(d.invite_code);
}

export async function inviteClient(e) {
  if (e) e.preventDefault();
  showError('invite-error', '');
  const input = document.getElementById('invite-full-name');
  try {
    const d = await apiFetch('/api/onboarding/invite-client', {
      method: 'POST',
      body: JSON.stringify({ full_name: input.value }),
    });
    input.value = '';
    showInviteResult(d);
    loadClients();
  } catch (ex) {
    showError('invite-error', ex.message);
  }
}

export async function renewInvite(patientId) {
  showError('invite-error', '');
  try {
    const d = await apiFetch(`/api/onboarding/invitations/${encodeURIComponent(patientId)}/renew`,
                             { method: 'POST' });
    showInviteResult(d);
    loadClients();
  } catch (ex) {
    showError('invite-error', ex.message);
  }
}

export function copyField(id) {
  const el = document.getElementById(id);
  if (el && el.value) navigator.clipboard?.writeText(el.value);
}

export function openClient(patientId, page = 'records') {
  setSelectedPatient(patientId);
  const selector = document.getElementById('patient-selector-input');
  if (selector) selector.value = patientId;
  const recPatId = document.getElementById('rec-patient-id');
  if (recPatId) recPatId.value = patientId;
  navigate(page);
}

/* -- Practitioner: secretaries --------------------------------------- */

async function loadStaff() {
  const list = document.getElementById('staff-list');
  if (!list) return;
  try {
    const d = await apiFetch('/api/onboarding/staff');
    list.innerHTML = d.staff.length
      ? d.staff.map(s => `
          <div class="user-card glass">
            <div class="user-avatar" style="background:linear-gradient(135deg,#818cf8,#4f46e5)">${escapeHtml(s.full_name.charAt(0))}</div>
            <div style="flex:1">
              <div style="font-weight:600">${escapeHtml(s.full_name)}</div>
              <div style="font-size:12px;color:var(--muted)">@${escapeHtml(s.username)}</div>
            </div>
            <span class="badge ${s.status === 'active' ? 'badge-shared' : 'badge-private'}">${s.status === 'active' ? 'Active' : 'Invited'}</span>
          </div>`).join('')
      : emptyState('No secretary yet.');
  } catch (e) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
  }
}

export async function inviteSecretary(e) {
  if (e) e.preventDefault();
  showError('secretary-error', '');
  const name = document.getElementById('secretary-full-name');
  const username = document.getElementById('secretary-username');
  try {
    const d = await apiFetch('/api/onboarding/invite-secretary', {
      method: 'POST',
      body: JSON.stringify({ full_name: name.value, username: username.value }),
    });
    name.value = '';
    username.value = '';
    document.getElementById('secretary-result').hidden = false;
    document.getElementById('secretary-result-username').textContent = d.username;
    document.getElementById('secretary-result-link').value = inviteLink(d.invite_code);
    loadStaff();
  } catch (ex) {
    showError('secretary-error', ex.message);
  }
}

/* -- Client: redeem an invitation on the login screen ---------------- */

export function showRedeem(code = '') {
  document.getElementById('login-form').style.display = 'none';
  document.getElementById('login-invite-link').style.display = 'none';
  document.getElementById('redeem-form').style.display = 'block';
  showError('login-error', '');
  showError('redeem-error', '');
  document.getElementById('inp-invite-code').value = code;
  document.getElementById(code ? 'inp-new-password' : 'inp-invite-code').focus();
}

export function showLogin() {
  document.getElementById('redeem-form').style.display = 'none';
  document.getElementById('login-form').style.display = 'block';
  document.getElementById('login-invite-link').style.display = 'block';
  showError('redeem-error', '');
}

export async function redeemInvite(e) {
  if (e) e.preventDefault();
  showError('redeem-error', '');
  const code = document.getElementById('inp-invite-code').value.trim();
  const password = document.getElementById('inp-new-password').value;
  if (password !== document.getElementById('inp-new-password2').value) {
    showError('redeem-error', 'The two passwords do not match.');
    return;
  }
  try {
    const d = await apiFetch('/api/onboarding/redeem', {
      method: 'POST',
      body: JSON.stringify({ enrollment_token: code, new_password: password }),
    });
    document.getElementById('redeem-form').reset();
    showLogin();
    document.getElementById('inp-username').value = d.username;
    const next = d.invited_by
      ? ` After signing in, open Consent Permissions to let ${d.invited_by} see your records.`  // xss-reviewed: only ever assigned to textContent
      : '';
    const ok = document.getElementById('login-success');
    ok.textContent = `Your account is ready. Your username is ${d.username}.${next}`;
    ok.style.display = 'block';
    document.getElementById('inp-password').focus();
  } catch (ex) {
    showError('redeem-error', ex.message);
  }
}

// Opening an invitation link (…/#invite=CODE) goes straight to the redeem form.
// The code is removed from the address bar and the history at once.
export function checkInviteLink() {
  const m = location.hash.match(/^#invite=([A-Za-z0-9_%-]+)$/);
  if (!m) return;
  history.replaceState(null, '', location.pathname + location.search);
  showRedeem(decodeURIComponent(m[1]));
}
