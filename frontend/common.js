// Shared across all pages: resolves the logged-in user via the session
// cookie (real auth - see backend/auth.py), gates pages behind login,
// renders the nav user chip + theme toggle, and role-aware nav visibility.

let _cachedUser = null;

async function whoami() {
    try {
        const res = await fetch('/api/auth/me');
        if (!res.ok) return null;
        const data = await res.json();
        _cachedUser = data.user || null;
        return _cachedUser;
    } catch (e) {
        return null;
    }
}

function getCurrentUser() {
    return _cachedUser;
}

// Back-compat no-op: every route now resolves the acting user from the
// session cookie, not a query param, so existing `fetch(apiUrl(...))` call
// sites across quiz.js/admin.js/etc keep working unchanged.
function apiUrl(path) {
    return path;
}

async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = 'login.html';
}

// Call once per protected page, after DOMContentLoaded. Redirects to the
// login page if there's no session; otherwise renders the user chip +
// theme toggle into `containerId` and applies role-aware nav visibility.
// Returns the user object (or null, if a redirect was triggered).
async function renderUserSwitcher(containerId) {
    const user = await whoami();
    if (!user) {
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = `login.html?next=${next}`;
        return null;
    }

    applyRoleAwareNav(user.role);

    const container = document.getElementById(containerId);
    if (container) {
        const wrap = document.createElement('div');
        wrap.className = 'user-switcher-wrap';

        const chip = document.createElement('span');
        chip.className = 'user-chip';
        chip.innerHTML =
            `<span class="user-chip-name">${escapeHtml(user.name)}</span>` +
            `<span class="role-badge role-${user.role}">${user.role}</span>`;

        const themeBtn = document.createElement('button');
        themeBtn.className = 'theme-toggle-btn';
        themeBtn.type = 'button';
        themeBtn.setAttribute('aria-label', 'Toggle dark mode');
        themeBtn.textContent = document.documentElement.dataset.theme === 'dark' ? '☀️' : '🌙';
        themeBtn.onclick = () => {
            toggleTheme();
            themeBtn.textContent = document.documentElement.dataset.theme === 'dark' ? '☀️' : '🌙';
        };

        const logoutBtn = document.createElement('button');
        logoutBtn.className = 'btn btn-secondary btn-sm';
        logoutBtn.type = 'button';
        logoutBtn.textContent = 'Log out';
        logoutBtn.onclick = logout;

        wrap.appendChild(chip);
        wrap.appendChild(themeBtn);
        wrap.appendChild(logoutBtn);
        container.appendChild(wrap);
    }

    return user;
}

// Elements tagged data-role-only="admin" or data-role-only="officer,admin"
// are shown only when the current user's role is in that list.
function applyRoleAwareNav(role) {
    document.querySelectorAll('[data-role-only]').forEach(el => {
        const allowed = el.getAttribute('data-role-only').split(',').map(r => r.trim());
        el.hidden = !allowed.includes(role);
    });
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

// ── Theme (dark/light, persisted) ────────────────────────────────────────

function initTheme() {
    const saved = localStorage.getItem('gl_theme');
    const theme = saved || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
}

function toggleTheme() {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('gl_theme', next);
}

// Apply the saved theme immediately (before DOMContentLoaded) to avoid a
// light-mode flash on load.
initTheme();

// ── Lightweight XP toast + confetti (used by quiz.js) ────────────────────

function showXpToast(xpInfo) {
    if (!xpInfo) return;
    const toast = document.createElement('div');
    toast.className = 'xp-toast';
    toast.innerHTML = xpInfo.leveled_up
        ? `🎉 Level up! Now level <strong>${xpInfo.level}</strong> · +${xpInfo.xp_gained} XP`
        : `+${xpInfo.xp_gained} XP`;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, xpInfo.leveled_up ? 2600 : 1400);

    if (xpInfo.leveled_up) fireConfetti();
}

function fireConfetti(count = 40) {
    const colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
    const layer = document.createElement('div');
    layer.className = 'confetti-layer';
    for (let i = 0; i < count; i++) {
        const piece = document.createElement('span');
        piece.className = 'confetti-piece';
        piece.style.left = `${Math.random() * 100}vw`;
        piece.style.background = colors[i % colors.length];
        piece.style.animationDelay = `${Math.random() * 0.3}s`;
        piece.style.transform = `rotate(${Math.random() * 360}deg)`;
        layer.appendChild(piece);
    }
    document.body.appendChild(layer);
    setTimeout(() => layer.remove(), 2200);
}

// ── Animated stat count-up (used by index.html dashboard) ───────────────

function animateCountUp(el, target, duration = 700) {
    const start = 0;
    const startTime = performance.now();
    function tick(now) {
        const progress = Math.min((now - startTime) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(start + (target - start) * eased);
        if (progress < 1) requestAnimationFrame(tick);
        else el.textContent = target;
    }
    requestAnimationFrame(tick);
}
