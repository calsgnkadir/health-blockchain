/* utils.js — VIP Health Vault UI Utilities */

export const API = '';

export function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}

export function getToken() {
  return localStorage.getItem('vhv_token');
}

export function setToken(token) {
  if (token) {
    localStorage.setItem('vhv_token', token);
  } else {
    localStorage.removeItem('vhv_token');
  }
}

export function getCurrentUser() {
  return JSON.parse(localStorage.getItem('vhv_user') || 'null');
}

export function setCurrentUser(user) {
  if (user) {
    localStorage.setItem('vhv_user', JSON.stringify(user));
  } else {
    localStorage.removeItem('vhv_user');
  }
}

export async function apiFetch(path, opts = {}) {
  let fullPath = path;
  if (fullPath.startsWith('/api/') && !fullPath.startsWith('/api/v1/')) {
    fullPath = '/api/v1' + fullPath.substring(4);
  }
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  // CSRF protection: append token header for unsafe methods
  const csrfToken = getCookie('csrf_token');
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }
  
  const res = await fetch(API + fullPath, { ...opts, headers });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(json.detail || 'An error occurred');
  }
  return json;
}

export function formatTs(ts) {
  return new Date(ts * 1000).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function formatTsFull(ts) {
  return new Date(ts * 1000).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function emptyState(msg) {
  return `<div class="empty-state"><div class="empty-icon-svg">
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#6B6882" stroke-width="1" stroke-linecap="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
    </svg>
  </div><p>${msg}</p></div>`;
}

export const ROLE_LABEL = { admin: 'Administrator', doctor: 'Doctor', vip_patient: 'VIP Patient' };

export function patientId() {
  const user = getCurrentUser();
  return user && user.role === 'vip_patient' ? user.patient_id : 'VIP-001';
}

// Centralized UI State Manager
export const appState = {
  currentUser: null,
  chainValid: true,
  activePage: 'dashboard',
  notificationsCount: 0,

  updateUser(user) {
    this.currentUser = user;
    this.render();
  },

  updateChain(valid) {
    this.chainValid = valid;
    this.render();
  },

  updatePage(page) {
    this.activePage = page;
    this.render();
  },

  updateNotifications(count) {
    this.notificationsCount = count;
    this.render();
  },

  render() {
    // 1. Render User Info
    if (this.currentUser) {
      const sbName = document.getElementById('sidebar-name');
      if (sbName) sbName.textContent = this.currentUser.full_name;
      const sbRole = document.getElementById('sidebar-role');
      if (sbRole) {
        if (this.currentUser.role === 'vip_patient') {
          sbRole.textContent = this.currentUser.patient_id === 'VIP-001' ? 'PAT-2024-0047' : this.currentUser.patient_id;
        } else {
          sbRole.textContent = ROLE_LABEL[this.currentUser.role] || this.currentUser.role;
        }
      }
      const sbAvatar = document.getElementById('sidebar-avatar');
      if (sbAvatar) sbAvatar.textContent = this.currentUser.full_name.charAt(0).toUpperCase();
      const tbUser = document.getElementById('topbar-user-name');
      if (tbUser) tbUser.textContent = this.currentUser.full_name;

      // Role-based navigation visibility
      const navUsers = document.getElementById('nav-users');
      if (navUsers) navUsers.style.display = (this.currentUser.role === 'admin') ? 'flex' : 'none';
      const navAudit = document.getElementById('nav-audit');
      if (navAudit) navAudit.style.display = (this.currentUser.role === 'admin' || this.currentUser.role === 'auditor') ? 'flex' : 'none';
      const navAdd = document.getElementById('nav-add');
      if (navAdd) navAdd.style.display = (this.currentUser.role === 'vip_patient') ? 'none' : 'flex';
    }

    // 2. Render Chain Pill
    const pill = document.getElementById('chain-pill');
    if (pill) {
      const dot = pill.querySelector('.chain-dot');
      const txt = document.getElementById('chain-pill-text');
      pill.className = 'chain-pill' + (this.chainValid ? '' : ' invalid');
      if (dot) dot.className = 'chain-dot ' + (this.chainValid ? 'valid' : 'invalid');
      if (txt) txt.textContent = this.chainValid ? 'Chain Valid' : 'Chain BROKEN!';
    }

    // 3. Render Notifications count
    const badge = document.getElementById('noti-badge-count');
    if (badge) {
      badge.textContent = this.notificationsCount;
      badge.style.display = this.notificationsCount > 0 ? 'inline-block' : 'none';
    }
  }
};

export function escapeHtml(str) {
  if (typeof str !== 'string') return str;
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

