const PROJECT_KEY = 'current_project_id';
const PROJECT_NAME_KEY = 'current_project_name';

const PROJECT_TYPE_LABELS = {
  local_culture:     '國小本土文化採購',
  general_books:     '國小一般圖書採購',
  local_culture_jh:  '國中本土文化採購',
  general_books_jh:  '國中一般圖書採購',
};
function projectTypeLabel(type) {
  return PROJECT_TYPE_LABELS[type] || type;
}
function isGeneralBooks(type) {
  return type === 'general_books' || type === 'general_books_jh';
}

const H_ALLOWED = [
  '喜閱網',
  '文化部中小學生優良課外讀物選介',
  '好書大家讀',
  '金鼎獎',
  '文化部Books from Taiwan等具高公信力推薦價值之圖書',
  '國民中小學新生閱讀推動活動入選書單',
  '圖書分級推薦書目、臺灣歷史文化分級推薦書目',
  '其他國內外具公信力單位辦理之獎項(請備註獎項名稱)',
  '學校自選(請備註原因)',
];

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function safeParseJson(str, fallback = {}) {
  if (str == null || str === '') return fallback;
  if (typeof str === 'object') return str;
  try {
    const parsed = JSON.parse(str);
    return parsed == null ? fallback : parsed;
  } catch {
    return fallback;
  }
}

function formatApiError(detail, status) {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map(item => {
      if (typeof item === 'string') return item;
      if (item && typeof item === 'object') {
        const loc = Array.isArray(item.loc)
          ? item.loc.filter(p => p !== 'body' && p !== 'query').join('.')
          : '';
        const msg = item.msg || JSON.stringify(item);
        return loc ? `${loc}：${msg}` : msg;
      }
      return String(item);
    }).join('；');
  }
  if (detail && typeof detail === 'object') {
    return detail.message || detail.msg || JSON.stringify(detail);
  }
  return status ? `請求失敗（HTTP ${status}）` : '請求失敗';
}

function getProjectId() {
  const s = parseInt(sessionStorage.getItem(PROJECT_KEY));
  if (s > 0) return s;
  const l = parseInt(localStorage.getItem(PROJECT_KEY));
  return l > 0 ? l : null;
}
function getProjectName() {
  return sessionStorage.getItem(PROJECT_NAME_KEY)
    || localStorage.getItem(PROJECT_NAME_KEY)
    || '未選擇專案';
}
function setProject(id, name) {
  sessionStorage.setItem(PROJECT_KEY, id);
  sessionStorage.setItem(PROJECT_NAME_KEY, name);
  localStorage.setItem(PROJECT_KEY, id);
  localStorage.setItem(PROJECT_NAME_KEY, name);
}
function clearProject() {
  sessionStorage.removeItem(PROJECT_KEY);
  sessionStorage.removeItem(PROJECT_NAME_KEY);
  localStorage.removeItem(PROJECT_KEY);
  localStorage.removeItem(PROJECT_NAME_KEY);
}

function requireProject(containerId) {
  const pid = getProjectId();
  if (pid) return pid;
  const label = document.getElementById('project-label');
  if (label) label.textContent = '目前專案：尚未選擇';
  const existing = document.getElementById('no-project-banner');
  if (existing) existing.remove();
  const banner = document.createElement('div');
  banner.id = 'no-project-banner';
  banner.className = 'alert alert-error';
  banner.style.marginBottom = '16px';
  banner.innerHTML = '尚未選擇採購專案，請先前往 <a href="/projects.html" style="font-weight:600;text-decoration:underline;color:inherit">採購專案</a> 頁面選擇或建立專案。';
  const target = (containerId && document.getElementById(containerId))
    || document.querySelector('.page')
    || document.body;
  if (target) target.prepend(banner);
  return null;
}

async function api(url, options = {}) {
  let res;
  try {
    res = await fetch(url, options);
  } catch {
    throw new Error('網路連線失敗，請確認系統是否正常運作');
  }
  if (res.status === 401) {
    window.location.href = '/login.html?expired=1';
    const err = new Error('登入已逾時，請重新登入');
    err.isAuthError = true;
    throw err;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(formatApiError(body.detail, res.status));
  }
  return res.json();
}

async function requireAuth() {
  try {
    const me = await api('/api/auth/me');
    const el = document.getElementById('user-name');
    if (el) el.textContent = me.display_name || me.username || '';
  } catch (e) {
    if (!e || !e.isAuthError) {
      window.location.href = '/login.html';
    }
    throw new Error('not auth');
  }
}

async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  clearProject();
  window.location.href = '/login.html';
}

let _toastTimer = null;
function showToast(msg, duration = 2500) {
  const t = document.getElementById('toast');
  if (!t) return;
  clearTimeout(_toastTimer);
  t.textContent = msg;
  t.classList.add('show');
  _toastTimer = setTimeout(() => {
    t.classList.remove('show');
    _toastTimer = null;
  }, duration);
}

function badge(status, type = 'match') {
  const cls = `badge badge-${esc(status)}`;
  const labels = {
    available: '可採購', already_owned: '已館藏',
    missing_isbn: 'ISBN缺失', invalid_isbn: 'ISBN無效',
    same_title_different_isbn: '書名重複不同ISBN',
    export_ready: '可匯出', needs_review: '需補資料',
    missing_required: '缺必填', unknown: '未知',
  };
  return `<span class="${cls}">${esc(labels[status] || status)}</span>`;
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
