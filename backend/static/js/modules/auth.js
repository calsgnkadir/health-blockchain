/* auth.js — VIP Health Vault UI Authentication Module */
import { apiFetch, setToken, setCurrentUser, getCurrentUser } from './utils.js';
import { updateNotificationsUI, addNotification } from './notifications.js';

export let mfaRequired = false;

export function resetLoginFormState() {
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

export function resetLoginForm(e) {
  if (e) e.preventDefault();
  resetLoginFormState();
}

export function fillCreds(u, p) {
  resetLoginFormState();
  document.getElementById('inp-username').value = u;
  document.getElementById('inp-password').value = p;
}

export function logout() {
  apiFetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
  setToken(null);
  setCurrentUser(null);
  resetLoginFormState();
  document.getElementById('page-login').classList.add('active');
  document.getElementById('page-login').style.display = 'block';
  document.getElementById('page-app').style.display = 'none';
  updateNotificationsUI();
}

export async function setup2FA() {
  const err = document.getElementById('security-error');
  if (err) err.style.display = 'none';
  
  try {
    const res = await apiFetch('/api/auth/2fa/setup', { method: 'POST' });
    document.getElementById('mfa-qr-code-img').src = res.qr_code;
    document.getElementById('mfa-secret-key').textContent = res.secret;
    document.getElementById('mfa-setup-section').style.display = 'block';
    document.getElementById('inp-2fa-verify-code').value = '';
    document.getElementById('inp-2fa-verify-code').focus();
  } catch(e) {
    if (err) {
      err.textContent = e.message;
      err.style.display = 'block';
    }
  }
}

export async function enable2FA() {
  const err = document.getElementById('security-error');
  const succ = document.getElementById('security-success');
  if (err) err.style.display = 'none';
  if (succ) succ.style.display = 'none';
  
  const code = document.getElementById('inp-2fa-verify-code').value.trim();
  if (!code) {
    if (err) {
      err.textContent = 'Please enter verification code.';
      err.style.display = 'block';
    }
    return;
  }
  
  try {
    const res = await apiFetch('/api/auth/2fa/enable', {
      method: 'POST',
      body: JSON.stringify({ code })
    });
    if (succ) {
      succ.textContent = res.message;
      succ.style.display = 'block';
    }
    
    if (window.loadSecuritySettings) {
      await window.loadSecuritySettings();
    }
  } catch(e) {
    if (err) {
      err.textContent = e.message;
      err.style.display = 'block';
    }
  }
}

export async function disable2FA() {
  const err = document.getElementById('security-error');
  const succ = document.getElementById('security-success');
  if (err) err.style.display = 'none';
  if (succ) succ.style.display = 'none';
  
  const code = document.getElementById('inp-2fa-disable-code').value.trim();
  if (!code) {
    if (err) {
      err.textContent = 'Please enter validation code to disable 2FA.';
      err.style.display = 'block';
    }
    return;
  }
  
  try {
    const res = await apiFetch('/api/auth/2fa/disable', {
      method: 'POST',
      body: JSON.stringify({ code })
    });
    if (succ) {
      succ.textContent = res.message;
      succ.style.display = 'block';
    }
    
    if (window.loadSecuritySettings) {
      await window.loadSecuritySettings();
    }
  } catch(e) {
    if (err) {
      err.textContent = e.message;
      err.style.display = 'block';
    }
  }
}

// Auto-bind login form submit
export function initAuthListeners() {
  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', async e => {
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
          setToken(data.access_token);
          setCurrentUser(data.user);
          resetLoginFormState();
          if (window.enterApp) {
            window.enterApp();
          }
        }
      } catch(ex) {
        err.textContent = ex.message;
        err.style.display = 'block';
      } finally {
        btxt.style.display = 'inline'; bspin.style.display = 'none';
        btn.disabled = false;
      }
    });
  }
}
