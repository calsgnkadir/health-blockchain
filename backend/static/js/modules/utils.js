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
  
  const res = await fetch(API + path, { ...opts, headers });
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
