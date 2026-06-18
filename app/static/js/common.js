const PROJECT_KEY = 'current_project_id';
const PROJECT_NAME_KEY = 'current_project_name';

function getProjectId() { return parseInt(sessionStorage.getItem(PROJECT_KEY)) || null; }
function getProjectName() { return sessionStorage.getItem(PROJECT_NAME_KEY) || '未選擇專案'; }
function setProject(id, name) {
  sessionStorage.setItem(PROJECT_KEY, id);
  sessionStorage.setItem(PROJECT_NAME_KEY, name);
}

async function api(url, options = {}) {
  const res = await fetch(url, options);
  if (res.status === 401) { window.location.href = '/login.html'; throw new Error('401'); }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

async function requireAuth() {
  try {
    const me = await api('/api/auth/me');
    const el = document.getElementById('user-name');
    if (el) el.textContent = me.display_name || me.username || '';
  } catch {
    window.location.href = '/login.html';
    throw new Error('not auth');
  }
}

async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/login.html';
}

function showToast(msg, duration = 2500) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}

function badge(status, type = 'match') {
  const cls = `badge badge-${status}`;
  const labels = {
    available: '可採購', already_owned: '已館藏',
    missing_isbn: 'ISBN缺失', invalid_isbn: 'ISBN無效',
    same_title_different_isbn: '書名重複不同ISBN',
    export_ready: '可匯出', needs_review: '需補資料',
    missing_required: '缺必填', unknown: '未知',
  };
  return `<span class="${cls}">${labels[status] || status}</span>`;
}

function formatCurrency(n) {
  if (n == null || isNaN(n)) return '—';
  return Number(n).toLocaleString('zh-TW');
}

function setNavActive(page) {
  document.querySelectorAll('.nav-steps a').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === '/' + page);
  });
}

function highlightNav() {
  const page = window.location.pathname.split('/').pop() || 'index.html';
  setNavActive(page);
}

document.addEventListener('DOMContentLoaded', highlightNav);
