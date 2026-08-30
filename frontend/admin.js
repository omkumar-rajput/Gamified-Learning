const API_BASE = '/api';

document.addEventListener('DOMContentLoaded', initAdmin);

async function initAdmin() {
    const user = await renderUserSwitcher('user-switcher-slot');
    if (!user) return;

    try {
        const [overviewRes, peopleRes, settingsRes] = await Promise.all([
            fetch(`${API_BASE}/admin/overview`),
            fetch(`${API_BASE}/admin/people`),
            fetch(`${API_BASE}/admin/settings`),
        ]);
        if (!overviewRes.ok) throw new Error(`admin/overview returned ${overviewRes.status}`);

        const overview = await overviewRes.json();
        document.getElementById('loading').hidden = true;
        renderOfficerTable(overview.officers);
        renderOrgCompetencies(overview.org_competency_scores);
        document.getElementById('admin-content').hidden = false;

        if (peopleRes.ok) renderPeopleTable((await peopleRes.json()).people);
        if (settingsRes.ok) renderAiSettings(await settingsRes.json());
    } catch (err) {
        console.error(err);
        document.getElementById('loading').innerHTML =
            '<p style="color:var(--danger)">Failed to load the admin overview — this page is admin-only.</p>';
        return;
    }

    document.getElementById('add-person-form').addEventListener('submit', onAddPerson);
    document.getElementById('ai-settings-form').addEventListener('submit', onSaveKey);
}

function scoreClass(score) {
    if (score === null || score === undefined) return 'mid';
    if (score >= 70) return 'high';
    if (score >= 40) return 'mid';
    return 'low';
}

function renderOfficerTable(officers) {
    const table = document.getElementById('officer-table');
    table.innerHTML = `
        <thead>
            <tr>
                <th>Officer</th>
                <th>Due Reviews</th>
                <th>Streak</th>
                <th>Gap Count</th>
                <th>Weakest Competency</th>
            </tr>
        </thead>
        <tbody>
            ${officers.map(o => `
                <tr>
                    <td>${o.name}</td>
                    <td>${o.due_count}</td>
                    <td>${o.streak} day${o.streak === 1 ? '' : 's'}</td>
                    <td>${o.gap_count}</td>
                    <td>${o.weakest_competency || '—'}</td>
                </tr>
            `).join('') || '<tr><td colspan="5" style="color:var(--text-muted);">No officers yet — add one below.</td></tr>'}
        </tbody>
    `;
}

function renderOrgCompetencies(orgScores) {
    const container = document.getElementById('org-competency-list');
    if (!orgScores.length) {
        container.innerHTML = '<p style="color:var(--text-muted);">No officer competency data yet.</p>';
        return;
    }
    container.innerHTML = `<div class="chart-card">${orgScores.map(c => {
        const score = c.avg_score;
        const cls = scoreClass(score);
        const weakest = c.weakest_officers.map(w => `${w.user_id.replace('demo_', '')} (${w.score}%)`).join(', ');
        return `
            <div class="competency-bar-row">
                <div class="competency-bar-header">
                    <span class="competency-bar-name">${c.name}</span>
                    <span class="competency-bar-score score-${cls}">${score === null ? 'No data' : score + '%'}</span>
                </div>
                <div class="competency-bar-track">
                    <div class="competency-bar-fill fill-${cls}" style="width:${score || 0}%"></div>
                </div>
                <div class="competency-meta">${c.officers_assessed} officer(s) assessed${weakest ? ' · Weakest: ' + weakest : ''}</div>
            </div>
        `;
    }).join('')}</div>`;
}

// ── Manage People ─────────────────────────────────────────────────────────

function renderPeopleTable(people) {
    const table = document.getElementById('people-table');
    table.innerHTML = `
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th></tr></thead>
        <tbody>${people.map(p => `
            <tr>
                <td>${escapeHtml(p.name)}</td>
                <td>${escapeHtml(p.email)}</td>
                <td><span class="role-badge role-${p.role}">${p.role}</span></td>
                <td><span class="status-pill ${p.active ? 'active' : 'inactive'}">${p.active ? 'Active' : 'Inactive'}</span></td>
                <td><button class="btn btn-secondary btn-sm" onclick="togglePersonActive('${p.id}', ${!p.active})">${p.active ? 'Deactivate' : 'Reactivate'}</button></td>
            </tr>
        `).join('')}</tbody>
    `;
}

async function togglePersonActive(id, nextActive) {
    try {
        const res = await fetch(`${API_BASE}/admin/people/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ active: nextActive }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Update failed');
        const peopleRes = await fetch(`${API_BASE}/admin/people`);
        renderPeopleTable((await peopleRes.json()).people);
    } catch (err) {
        alert(err.message);
    }
}

async function onAddPerson(e) {
    e.preventDefault();
    const msg = document.getElementById('add-person-msg');
    msg.textContent = '';
    try {
        const res = await fetch(`${API_BASE}/admin/people`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: document.getElementById('new-person-name').value.trim(),
                email: document.getElementById('new-person-email').value.trim(),
                password: document.getElementById('new-person-password').value,
                role: document.getElementById('new-person-role').value,
            }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Could not create account');
        msg.style.color = 'var(--success)';
        msg.textContent = `✅ Created ${data.user.name}`;
        document.getElementById('add-person-form').reset();
        const peopleRes = await fetch(`${API_BASE}/admin/people`);
        renderPeopleTable((await peopleRes.json()).people);
        const overviewRes = await fetch(`${API_BASE}/admin/overview`);
        if (overviewRes.ok) {
            const overview = await overviewRes.json();
            renderOfficerTable(overview.officers);
            renderOrgCompetencies(overview.org_competency_scores);
        }
        fireConfetti(20);
    } catch (err) {
        msg.style.color = 'var(--danger)';
        msg.textContent = err.message;
    }
}

// ── AI Settings ──────────────────────────────────────────────────────────

function renderAiSettings(data) {
    const status = document.getElementById('current-key-status');
    if (data.ai_api_key_masked) {
        status.innerHTML = `<span class="masked-key">${data.ai_api_key_masked}</span> ` +
            `<span style="color:var(--text-muted); font-size:0.85rem;">— set here, takes priority over env vars</span>`;
    } else if (data.has_env_fallback) {
        status.innerHTML = `<span style="color:var(--success);">Using an environment-variable key (no key set here).</span>`;
    } else {
        status.innerHTML = `<span style="color:var(--danger);">No AI key configured yet — uploads will fail until one is set.</span>`;
    }
}

async function onSaveKey(e) {
    e.preventDefault();
    const input = document.getElementById('ai-key-input');
    if (!input.value.trim()) return;
    try {
        const res = await fetch(`${API_BASE}/admin/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ai_api_key: input.value.trim() }),
        });
        if (!res.ok) throw new Error('Could not save key');
        input.value = '';
        const settingsRes = await fetch(`${API_BASE}/admin/settings`);
        renderAiSettings(await settingsRes.json());
    } catch (err) {
        alert(err.message);
    }
}
