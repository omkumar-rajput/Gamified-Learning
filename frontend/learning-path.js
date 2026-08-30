const API_BASE = '/api';

document.addEventListener('DOMContentLoaded', initLearningPath);

async function initLearningPath() {
    renderUserSwitcher('user-switcher-slot');

    try {
        const res = await fetch(apiUrl(`${API_BASE}/recommendations`));
        const data = await res.json();

        document.getElementById('loading').hidden = true;

        if (!data.recommendations || data.recommendations.length === 0) {
            document.getElementById('empty-state').hidden = false;
            return;
        }

        renderRecommendations(data.recommendations);
        document.getElementById('recommendations-list').hidden = false;
    } catch (err) {
        console.error(err);
        document.getElementById('loading').innerHTML =
            '<p style="color:var(--danger)">Failed to load recommendations. Is the backend running?</p>';
    }
}

function renderRecommendations(recommendations) {
    const container = document.getElementById('recommendations-list');
    container.innerHTML = recommendations.map(rec => `
        <div class="recommendation-card priority-${rec.priority}">
            <div class="recommendation-header">
                <span class="recommendation-title">${rec.competency_name}</span>
                <span class="priority-badge priority-${rec.priority}">${rec.priority} priority</span>
            </div>
            <div class="recommendation-desc">Current proficiency: <strong>${rec.score}%</strong></div>
            <div class="course-list">
                ${rec.courses.length > 0 ? rec.courses.map(course => `
                    <div class="course-item">
                        <div class="course-info">
                            <div class="course-title">${course.title}</div>
                            <div class="course-meta">${course.provider} · ${course.duration_hours}h · ${course.id}</div>
                        </div>
                        <a class="btn-enroll" href="${course.url}" target="_blank" rel="noopener">Enroll on iGOT →</a>
                    </div>
                `).join('') : '<p style="color:var(--text-muted); font-size:0.85rem;">No matching iGOT course found in the catalog yet.</p>'}
            </div>
        </div>
    `).join('');
}
