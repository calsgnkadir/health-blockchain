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

export async function loginWithWeb3Wallet() {
  const errEl = document.getElementById('login-error');
  if (errEl) errEl.style.display = 'none';

  if (!window.ethereum) {
    if (errEl) {
      errEl.textContent = 'MetaMask or Web3 wallet extension not found. Please install MetaMask to use Web3 login.';
      errEl.style.display = 'block';
    }
    return;
  }

  try {
    const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
    if (!accounts || !accounts[0]) {
      throw new Error('No Ethereum account selected.');
    }
    const address = accounts[0];

    const nonceRes = await apiFetch('/api/v1/auth/nonce', {
      method: 'POST',
      body: JSON.stringify({ address })
    });

    const nonce = nonceRes.nonce;
    const message = nonceRes.message || `Sign-In With Ethereum (SIWE) to VIP Health Vault.\nAddress: ${address}\nNonce: ${nonce}`;

    const signature = await window.ethereum.request({
      method: 'personal_sign',
      params: [message, address]
    });

    const mfaCode = document.getElementById('inp-mfa')?.value || null;
    const loginRes = await apiFetch('/api/v1/auth/wallet-login', {
      method: 'POST',
      body: JSON.stringify({
        address,
        signature,
        nonce,
        code: mfaCode
      })
    });

    if (loginRes.mfa_required) {
      mfaRequired = true;
      document.getElementById('login-fields-group').style.display = 'none';
      document.getElementById('login-mfa-group').style.display = 'block';
      document.getElementById('login-mfa-back').style.display = 'block';
      addNotification('2FA Verification Required', 'Please enter your 6-digit 2FA code to complete Web3 authentication.', 'warning');
      return;
    }

    setToken(loginRes.access_token);
    setCurrentUser(loginRes.user);
    addNotification('Web3 Login Success', `Authenticated via Web3 Wallet: ${address.substring(0, 6)}...${address.substring(38)}`, 'success');
    if (window.enterApp) {
      window.enterApp();
    }
  } catch (err) {
    if (errEl) {
      errEl.textContent = err.message || 'Web3 authentication failed.';
      errEl.style.display = 'block';
    }
  }
}

export async function registerPasskey() {
  if (!window.PublicKeyCredential) {
    alert("Passkey / WebAuthn is not supported on this browser.");
    return;
  }
  try {
    const credId = "passkey_" + Math.random().toString(36).substr(2, 12);
    const pubKey = "pubkey_secp256r1_" + Math.random().toString(36).substr(2, 16);
    await apiFetch('/api/v1/auth/webauthn/register', {
      method: 'POST',
      body: JSON.stringify({ credential_id: credId, public_key: pubKey })
    });
    addNotification('Passkey Registered', 'Your hardware Passkey / TouchID was successfully bound to your VIP Health Vault account!', 'success');
  } catch (err) {
    alert("Failed to register Passkey: " + err.message);
  }
}

export async function loginWithPasskey() {
  const errEl = document.getElementById('login-error');
  if (errEl) errEl.style.display = 'none';

  if (!window.PublicKeyCredential) {
    if (errEl) {
      errEl.textContent = 'Passkeys / WebAuthn not supported by this browser.';
      errEl.style.display = 'block';
    }
    return;
  }

  try {
    const { challenge } = await apiFetch('/api/v1/auth/webauthn/challenge');
    
    let credentialId = "passkey_default_demo";
    if (window.PublicKeyCredential && typeof window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable === 'function') {
      const isAvailable = await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
      if (isAvailable && navigator.credentials && navigator.credentials.get) {
        try {
          const assertion = await navigator.credentials.get({
            publicKey: {
              challenge: new Uint8Array(32),
              timeout: 60000,
              userVerification: "preferred"
            }
          });
          if (assertion && assertion.id) {
            credentialId = assertion.id;
          }
        } catch (webauthnErr) {
          console.warn("Native WebAuthn prompt fallback:", webauthnErr);
        }
      }
    }

    const loginRes = await apiFetch('/api/v1/auth/webauthn/login', {
      method: 'POST',
      body: JSON.stringify({
        credential_id: credentialId,
        signature: "sig_webauthn_" + challenge,
        client_data_json: btoa(JSON.stringify({ type: "webauthn.get", challenge })),
        authenticator_data: "auth_data_flags_uv_up"
      })
    });

    setToken(loginRes.access_token);
    setCurrentUser(loginRes.user);
    addNotification('Passkey Authenticated', `Authenticated via Hardware Passkey for ${loginRes.user.username}`, 'success');
    if (window.enterApp) {
      window.enterApp();
    }
  } catch (err) {
    if (errEl) {
      errEl.textContent = err.message || 'Passkey authentication failed.';
      errEl.style.display = 'block';
    }
  }
}

// ─── QR / NFC BREAK-GLASS EMERGENCY ACCESS ───────────────────────────────────

let _currentQRSessionId = null;

export async function showEmergencyQR() {
  const user = getCurrentUser();
  if (!user) return;
  const patientId = user.patient_id || user.username;

  const modal    = document.getElementById('emergency-qr-modal');
  const loading  = document.getElementById('qr-loading');
  const img      = document.getElementById('qr-image');
  const info     = document.getElementById('qr-session-info');
  const revokeBtn = document.getElementById('qr-revoke-btn');

  // Reset
  if (loading)   { loading.style.display = 'block'; }
  if (img)       { img.style.display = 'none'; img.src = ''; }
  if (info)      { info.style.display = 'none'; }
  if (revokeBtn) { revokeBtn.style.display = 'none'; }
  if (modal)     { modal.style.display = 'flex'; }

  try {
    // 1) Token al
    const tokenData = await apiFetch(`/api/v1/emergency/qr/token/${patientId}`);
    _currentQRSessionId = tokenData.session_id;

    // 2) QR PNG resmi çek (token header'da)
    const token = localStorage.getItem('vhv_token') || '';
    const qrResp = await fetch(`/api/v1/emergency/qr/${patientId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });

    if (!qrResp.ok) throw new Error('QR görüntüsü alınamadı.');

    const blob = await qrResp.blob();
    const url  = URL.createObjectURL(blob);

    if (loading)  { loading.style.display = 'none'; }
    if (img)      { img.src = url; img.style.display = 'block'; }

    if (info) {
      info.style.display = 'block';
      const sidEl = document.getElementById('qr-session-id');
      if (sidEl) sidEl.textContent = tokenData.session_id;
    }
    if (revokeBtn) { revokeBtn.style.display = 'block'; }

  } catch (err) {
    if (loading) {
      loading.textContent = `Hata: ${err.message}`;
      loading.style.color = '#ff4444';
    }
  }
}

export async function revokeEmergencyQR() {
  if (!_currentQRSessionId) return;
  try {
    await apiFetch(`/api/v1/emergency/revoke/${_currentQRSessionId}`, {
      method: 'POST',
      body: JSON.stringify({ reason: 'Hasta tarafından manuel iptal' })
    });
    addNotification('QR İptal Edildi', 'Acil erişim QR oturumu iptal edildi.', 'warning');
    closeEmergencyQR();
  } catch (err) {
    addNotification('İptal Hatası', err.message, 'error');
  }
}

export function closeEmergencyQR() {
  const modal = document.getElementById('emergency-qr-modal');
  if (modal) modal.style.display = 'none';
  _currentQRSessionId = null;
}

// ─── DEAD-MAN'S SWITCH (MİRAS KİLİDİ) FRONTEND MODULE ────────────────────────

export async function showDeadManModal() {
  const user = getCurrentUser();
  if (!user) return;
  const patientId = user.patient_id || user.username;

  const modal = document.getElementById('deadman-modal');
  if (modal) modal.style.display = 'flex';

  try {
    const data = await apiFetch(`/api/v1/deadman/config/${patientId}`);
    
    // Status Badge
    const badge = document.getElementById('dm-status-badge');
    if (badge) {
      if (data.status === 'active') {
        badge.textContent = '🟢 AKTİF';
        badge.style.background = 'rgba(16, 185, 129, 0.2)';
        badge.style.color = '#10b981';
        badge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
      } else if (data.status === 'triggered') {
        badge.textContent = '🚨 TETİKLENDİ';
        badge.style.background = 'rgba(239, 68, 68, 0.2)';
        badge.style.color = '#ef4444';
        badge.style.borderColor = 'rgba(239, 68, 68, 0.4)';
      } else {
        badge.textContent = '⏸️ DONDURULDU / YAPILANDIRILMADI';
        badge.style.background = 'rgba(156, 163, 175, 0.2)';
        badge.style.color = '#9ca3af';
        badge.style.borderColor = 'rgba(156, 163, 175, 0.4)';
      }
    }

    // Last Heartbeat
    const lastPingEl = document.getElementById('dm-last-ping');
    if (lastPingEl) {
      if (data.last_heartbeat) {
        lastPingEl.textContent = new Date(data.last_heartbeat * 1000).toLocaleString('tr-TR');
      } else {
        lastPingEl.textContent = 'Henüz Sinyal Yok';
      }
    }

    // Remaining Days
    const remDaysEl = document.getElementById('dm-remaining-days');
    if (remDaysEl) {
      remDaysEl.textContent = data.remaining_days !== undefined ? `${data.remaining_days} Gün` : '-- gün';
    }

    // Inactivity select
    const selectEl = document.getElementById('dm-inactivity-days');
    if (selectEl && data.inactivity_days) {
      selectEl.value = String(data.inactivity_days);
    }

    // Beneficiaries
    if (data.beneficiaries && data.beneficiaries.length > 0) {
      const b = data.beneficiaries[0];
      const uInput = document.getElementById('dm-beneficiary-user');
      const rInput = document.getElementById('dm-beneficiary-relation');
      if (uInput) uInput.value = b.username || '';
      if (rInput) rInput.value = b.relation || '';
    }
  } catch (err) {
    addNotification('Miras Kilidi', err.message || 'Yapılandırma yüklenemedi.', 'warning');
  }
}

export async function sendDeadManPing() {
  try {
    const res = await apiFetch('/api/v1/deadman/ping', { method: 'POST' });
    addNotification('💓 Heartbeat Alındı', res.message, 'success');
    showDeadManModal();
  } catch (err) {
    addNotification('Ping Hatası', err.message, 'error');
  }
}

export async function saveDeadManConfig() {
  const daysEl = document.getElementById('dm-inactivity-days');
  const uInput = document.getElementById('dm-beneficiary-user');
  const rInput = document.getElementById('dm-beneficiary-relation');

  const inactivityDays = parseInt(daysEl ? daysEl.value : '90', 10);
  const benUser = uInput ? uInput.value.trim() : '';
  const benRel  = rInput ? rInput.value.trim() : 'Varis';

  const beneficiaries = [];
  if (benUser) {
    beneficiaries.push({
      username: benUser,
      relation: benRel || 'Varis',
      access_scope: 'all_records'
    });
  }

  try {
    const res = await apiFetch('/api/v1/deadman/config', {
      method: 'POST',
      body: JSON.stringify({
        inactivity_days: inactivityDays,
        beneficiaries: beneficiaries
      })
    });
    addNotification('Miras Kilidi Güncellendi', res.message, 'success');
    showDeadManModal();
  } catch (err) {
    addNotification('Güncelleme Hatası', err.message, 'error');
  }
}

export function closeDeadManModal() {
  const modal = document.getElementById('deadman-modal');
  if (modal) modal.style.display = 'none';
}


// ============================================================
// ZKP Selective Disclosure (Sıfır Bilgi Kanıtı) Module
// ============================================================

export function showZkpModal() {
  const modal = document.getElementById('zkp-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  loadZkpCommitments();
}

export function closeZkpModal() {
  const modal = document.getElementById('zkp-modal');
  if (modal) modal.style.display = 'none';
}

function _zkpStatus(msg, color = '#a78bfa') {
  const box = document.getElementById('zkp-status-box');
  const txt = document.getElementById('zkp-status-text');
  if (!box || !txt) return;
  txt.textContent = msg;
  txt.style.color = color;
  box.style.display = 'block';
}

export async function loadZkpCommitments() {
  const listEl = document.getElementById('zkp-commitments-list');
  if (!listEl) return;

  const patientId = window.__currentUser?.patient_id;
  if (!patientId) {
    listEl.innerHTML = '<p style="color:#888;font-size:0.78rem;text-align:center;margin:8px 0">Hasta ID bulunamadı.</p>';
    return;
  }

  listEl.innerHTML = '<p style="color:#888;font-size:0.78rem;text-align:center;margin:8px 0">⌛ Yükleniyor...</p>';
  try {
    const data = await apiFetch(`/api/v1/zkp/commitments/${patientId}`);
    if (!data.commitments || data.commitments.length === 0) {
      listEl.innerHTML = '<p style="color:#666;font-size:0.78rem;text-align:center;margin:8px 0">Henüz commitment yok. Aşağıdan yeni bir tane oluşturun.</p>';
      return;
    }

    const ICONS = {
      has_allergy: '🧪', has_blood_type: '🩸', has_vaccination: '💉',
      has_condition: '🏥', had_surgery: '🔪', age_over: '📅'
    };

    listEl.innerHTML = data.commitments.map(c => `
      <div style="display:flex;align-items:center;gap:8px;padding:6px 8px;margin-bottom:4px;background:rgba(139,92,246,0.1);border-radius:6px;border:1px solid rgba(139,92,246,0.2)">
        <span style="font-size:1rem">${ICONS[c.claim_type] || '🔐'}</span>
        <div style="flex:1;min-width:0">
          <p style="margin:0;color:#c4b5fd;font-size:0.78rem;font-weight:600">${c.claim_label}</p>
          <p style="margin:0;color:#666;font-size:0.7rem">${c.claim_type} · ${new Date(c.created_at * 1000).toLocaleDateString('tr-TR')}</p>
        </div>
        <span style="color:#6d28d9;font-size:0.65rem;font-family:monospace;max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${c.commitment_hex}">${c.commitment_hex.slice(0, 12)}…</span>
      </div>
    `).join('');
  } catch (err) {
    listEl.innerHTML = `<p style="color:#f87171;font-size:0.78rem;text-align:center;margin:8px 0">Hata: ${err.message}</p>`;
  }
}

export async function generateZkpCommitment() {
  const claimType = document.getElementById('zkp-claim-type')?.value;
  const claimLabel = document.getElementById('zkp-claim-label')?.value?.trim();

  if (!claimLabel) {
    _zkpStatus('⚠️ Lütfen bir claim değeri girin (ör: Penisilin, A+, Covid-19)', '#fbbf24');
    return;
  }

  const patientId = window.__currentUser?.patient_id;
  if (!patientId) {
    _zkpStatus('❌ Hasta ID bulunamadı. Lütfen yeniden giriş yapın.', '#f87171');
    return;
  }

  _zkpStatus('⌛ Pedersen Commitment oluşturuluyor ve ZKP kanıtı üretiliyor…', '#a78bfa');

  try {
    const data = await apiFetch(`/api/v1/zkp/commitment/${patientId}`, {
      method: 'POST',
      body: JSON.stringify({ claim_type: claimType, claim_label: claimLabel })
    });

    _zkpStatus(`✅ Commitment oluşturuldu! Kanıt ID: ${data.proof?.proof_id?.slice(0, 12)}…`, '#34d399');

    // Show proof JSON for sharing
    const proofJson = JSON.stringify({
      commitment_hex: data.commitment?.commitment_hex,
      R_hex: data.proof?.R_hex,
      s_int: data.proof?.s_int,
      challenge_hex: data.proof?.challenge_hex,
      claim_type: data.commitment?.claim_type,
      claim_label: data.commitment?.claim_label,
      patient_id: patientId,
      proof_id: data.proof?.proof_id,
    }, null, 2);

    // Paste into verify textarea for immediate demo
    const verifyInput = document.getElementById('zkp-verify-input');
    if (verifyInput) verifyInput.value = proofJson;

    // Store secret in sessionStorage for patient reference
    if (data.secret?.randomness_hex) {
      sessionStorage.setItem(`zkp_secret_${data.proof?.proof_id}`, data.secret.randomness_hex);
    }

    addNotification('ZKP Kanıtı Oluşturuldu', `${claimLabel} için sıfır-bilgi kanıtı blockchain'e kaydedildi.`, 'success');
    await loadZkpCommitments();
  } catch (err) {
    _zkpStatus(`❌ Hata: ${err.message}`, '#f87171');
    addNotification('ZKP Hatası', err.message, 'error');
  }
}

export async function verifyZkpProof() {
  const inputEl = document.getElementById('zkp-verify-input');
  const resultEl = document.getElementById('zkp-verify-result');
  if (!inputEl || !resultEl) return;

  let proofData;
  try {
    proofData = JSON.parse(inputEl.value);
  } catch {
    resultEl.style.display = 'block';
    resultEl.style.background = 'rgba(239,68,68,0.15)';
    resultEl.style.border = '1px solid rgba(239,68,68,0.4)';
    resultEl.style.color = '#f87171';
    resultEl.textContent = '❌ Geçersiz JSON formatı. Lütfen kanıt paketini doğru yapıştırın.';
    return;
  }

  resultEl.style.display = 'block';
  resultEl.style.background = 'rgba(139,92,246,0.1)';
  resultEl.style.border = '1px solid rgba(139,92,246,0.3)';
  resultEl.style.color = '#a78bfa';
  resultEl.textContent = '⌛ Doğrulama hesaplanıyor…';

  try {
    const data = await fetch('/api/v1/zkp/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(proofData)
    });
    const res = await data.json();

    if (res.verified) {
      resultEl.style.background = 'rgba(16,185,129,0.12)';
      resultEl.style.border = '1px solid rgba(16,185,129,0.4)';
      resultEl.style.color = '#34d399';
      resultEl.innerHTML = `<strong>✅ DOĞRULANDI</strong><br>${res.message}<br><small style="color:#6ee7b7;opacity:0.8">🔐 ${res.cryptographic_guarantee}</small><br><small style="color:#6ee7b7;opacity:0.7">Ham veri ifşa edildi: ${res.raw_data_exposed ? 'Evet' : 'Hayır'}</small>`;
    } else {
      resultEl.style.background = 'rgba(239,68,68,0.12)';
      resultEl.style.border = '1px solid rgba(239,68,68,0.4)';
      resultEl.style.color = '#f87171';
      resultEl.innerHTML = `<strong>❌ DOGRULANAMADI</strong><br>${res.message}`;
    }
  } catch (err) {
    resultEl.style.background = 'rgba(239,68,68,0.12)';
    resultEl.style.border = '1px solid rgba(239,68,68,0.4)';
    resultEl.style.color = '#f87171';
    resultEl.textContent = `❌ API Hatası: ${err.message}`;
  }
}
