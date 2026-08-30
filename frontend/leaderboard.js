const API_BASE = '/api';

document.addEventListener('DOMContentLoaded', initLeaderboard);

async function initLeaderboard() {
    const user = await renderUserSwitcher('user-switcher-slot');
    if (!user) return;

    try {
        const res = await fetch(`${API_BASE}/leaderboard`);
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        const data = await res.json();

        renderMyXp(data.me);
        renderLeaderboard(data.leaderboard, user.id);

        document.getElementById('loading').hidden = true;
        document.getElementById('leaderboard-list').hidden = false;
    } catch (err) {
        console.error(err);
        document.getElementById('loading').innerHTML =
            '<p style="color:var(--danger)">Failed to load the leaderboard.</p>';
    }
}

function renderMyXp(me) {
    const pct = Math.round((me.xp_into_level / me.xp_for_next_level) * 100);
    document.getElementById('my-xp-card').innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0.5rem;">
            <h3 style="margin:0;">Level ${me.level}</h3>
            <span style="color:var(--text-muted); font-size:0.85rem;">${me.xp_into_level} / ${me.xp_for_next_level} XP to next level</span>
        </div>
        <div class="competency-bar-track"><div class="competency-bar-fill fill-high" style="width:${pct}%"></div></div>
        <div class="competency-meta">${me.xp_total} total XP</div>
    `;
}

function renderLeaderboard(rows, myUserId) {
    const container = document.getElementById('leaderboard-list');
    if (!rows.length) {
        container.innerHTML = '<p style="color:var(--text-muted); text-align:center;">No reviews yet — be the first on the board.</p>';
        return;
    }
    container.innerHTML = rows.map((r, i) => `
        <div class="leaderboard-row rank-${i + 1}" style="${r.user_id === myUserId ? 'border-color:var(--primary);' : ''}">
            <div class="leaderboard-rank">${i < 3 ? ['🥇', '🥈', '🥉'][i] : i + 1}</div>
            <div class="leaderboard-name">${escapeHtml(r.name)} <span class="role-badge role-${r.role}">${r.role}</span></div>
            <div style="color:var(--text-muted); font-size:0.85rem;">Lv ${r.level}</div>
            <div class="leaderboard-xp">${r.xp} XP</div>
        </div>
    `).join('');
}
