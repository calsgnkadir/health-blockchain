/* notifications.js — VIP Health Vault UI Notifications Module */
import { apiFetch, patientId, getCurrentUser } from './utils.js';

let localNotificationsCache = [];

export function getLocalNotifications() {
  const currentUser = getCurrentUser();
  const key = `vhv_notifications_${currentUser ? currentUser.username : 'guest'}`;
  try {
    return JSON.parse(localStorage.getItem(key) || '[]');
  } catch (e) {
    return [];
  }
}

export function saveLocalNotifications(list) {
  const currentUser = getCurrentUser();
  const key = `vhv_notifications_${currentUser ? currentUser.username : 'guest'}`;
  localStorage.setItem(key, JSON.stringify(list));
}

export function addNotification(title, text, type = 'info') {
  const list = getLocalNotifications();
  const noti = {
    id: 'local_' + Date.now() + Math.random().toString(36).substr(2, 5),
    title,
    text,
    type,
    time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
    date: new Date().toLocaleDateString('en-GB'),
    read: false,
    is_local: true
  };
  list.unshift(noti);
  saveLocalNotifications(list);
  updateNotificationsUI();
}

export async function fetchBackendNotifications() {
  const currentUser = getCurrentUser();
  if (!currentUser) return [];
  try {
    const pid = patientId();
    const res = await apiFetch(`/api/notifications/${pid}`);
    return (res.notifications || []).map(n => {
      const dateObj = new Date(n.timestamp * 1000);
      return {
        id: n.id,
        title: n.title,
        text: n.message,
        type: n.severity || 'info',
        time: dateObj.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
        date: dateObj.toLocaleDateString('en-GB'),
        read: n.read,
        is_local: false,
        timestamp: n.timestamp
      };
    });
  } catch (e) {
    console.error("Failed to fetch backend notifications:", e);
    return [];
  }
}

// Global cached notifications list
export function getNotifications() {
  const localList = getLocalNotifications();
  return [...localList, ...localNotificationsCache];
}

export async function updateNotificationsUI() {
  const badge = document.getElementById('noti-badge-count');
  const listEl = document.getElementById('noti-list');
  const currentUser = getCurrentUser();
  if (!currentUser) {
    if (badge) badge.style.display = 'none';
    if (listEl) listEl.innerHTML = '<div style="padding: 16px; text-align: center; color: var(--muted); font-size: 12px;">No alerts</div>';
    return;
  }

  // Fetch backend notifications asynchronously and update UI on load
  const backendList = await fetchBackendNotifications();
  localNotificationsCache = backendList;

  const localList = getLocalNotifications();
  const combined = [...localList, ...backendList];
  
  // Sort by date/time (we can use timestamp if available, otherwise estimate)
  combined.sort((a, b) => {
    const timeA = a.is_local ? Date.now() : (a.timestamp * 1000);
    const timeB = b.is_local ? Date.now() : (b.timestamp * 1000);
    return timeB - timeA;
  });

  const unreadCount = combined.filter(n => !n.read).length;

  if (badge) {
    if (unreadCount > 0) {
      badge.textContent = unreadCount;
      badge.style.display = 'block';
    } else {
      badge.style.display = 'none';
    }
  }

  if (listEl) {
    if (combined.length === 0) {
      listEl.innerHTML = '<div style="padding: 16px; text-align: center; color: var(--muted); font-size: 12px;">No new alerts</div>';
    } else {
      listEl.innerHTML = combined.map(n => {
        let typeDotClass = 'noti-dot-info';
        if (n.type === 'warning' || n.type === 'danger') typeDotClass = 'noti-dot-warning';
        if (n.type === 'success') typeDotClass = 'noti-dot-success';

        return `
          <div class="noti-item" onclick="markAsRead('${n.id}')">
            <div class="noti-title-row">
              <span class="noti-title">
                <span class="noti-icon-dot ${typeDotClass}"></span>
                ${n.title}
              </span>
              <span class="noti-time">${n.time}</span>
            </div>
            <div class="noti-text" style="${n.read ? 'color: var(--muted);' : 'font-weight: 500;'}">${n.text}</div>
            <div style="font-size: 9px; color: var(--muted); text-align: right; margin-top: 4px;">${n.date}</div>
          </div>
        `;
      }).join('');
    }
  }
}

export function toggleNotifications(event) {
  if (event) event.stopPropagation();
  const dropdown = document.getElementById('noti-dropdown');
  if (!dropdown) return;
  const isVisible = dropdown.style.display === 'block';
  
  closeAllDropdowns();

  if (!isVisible) {
    dropdown.style.display = 'block';
    markAllAsRead();
  }
}

export function closeAllDropdowns() {
  const dropdown = document.getElementById('noti-dropdown');
  if (dropdown) dropdown.style.display = 'none';
}

export async function markAsRead(id) {
  if (id.startsWith('local_')) {
    const list = getLocalNotifications();
    const item = list.find(n => n.id === id);
    if (item) {
      item.read = true;
      saveLocalNotifications(list);
      updateNotificationsUI();
    }
  } else {
    try {
      const pid = patientId();
      await apiFetch(`/api/notifications/${pid}/${id}/read`, { method: 'POST' });
      updateNotificationsUI();
    } catch (e) {
      console.error("Failed to mark backend notification as read:", e);
    }
  }
}

export async function markAllAsRead() {
  // Mark local as read
  const localList = getLocalNotifications();
  localList.forEach(n => n.read = true);
  saveLocalNotifications(localList);

  // Mark backend as read
  const pid = patientId();
  for (const n of localNotificationsCache) {
    if (!n.read) {
      try {
        await apiFetch(`/api/notifications/${pid}/${n.id}/read`, { method: 'POST' });
      } catch (e) {
        console.error(e);
      }
    }
  }

  updateNotificationsUI();
}

export function clearAllNotifications(event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  saveLocalNotifications([]);
  // Note: Backend notifications are read-only / persistence is managed by backend
  updateNotificationsUI();
}
