let shareQuestions = [];
let shareIndex = 0;

document.addEventListener('DOMContentLoaded', initShare);

async function initShare() {
    const themeBtn = document.getElementById('theme-btn');
    themeBtn.textContent = document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙';
    themeBtn.onclick = () => {
        toggleTheme();
        themeBtn.textContent = document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙';
    };

    const token = new URLSearchParams(window.location.search).get('token');
    if (!token) {
        showError('No share token in the URL.');
        return;
    }

    try {
        const res = await fetch(`/api/share/${encodeURIComponent(token)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'This share link is invalid or has expired.');

        shareQuestions = data.questions || [];
        document.getElementById('share-title').textContent = data.title;
        document.getElementById('share-subtitle').textContent =
            `Shared by ${data.shared_by} · ${shareQuestions.length} question${shareQuestions.length === 1 ? '' : 's'}`;

        document.getElementById('loading').hidden = true;
        document.getElementById('quiz-container').hidden = false;
        renderShareQuestion();
    } catch (err) {
        showError(err.message);
    }
}

function showError(message) {
    document.getElementById('loading').hidden = true;
    document.getElementById('share-subtitle').textContent = message;
}

function renderShareQuestion() {
    const container = document.getElementById('quiz-container');

    if (shareIndex >= shareQuestions.length) {
        container.innerHTML = `
            <article class="card done-state">
                <h2>All done! 🎉</h2>
                <p>Want your own spaced-repetition schedule, XP, and competency dashboard?</p>
                <a href="signup.html" class="btn btn-primary">Create a free account</a>
            </article>
        `;
        return;
    }

    const q = shareQuestions[shareIndex];
    const hasOptions = q.options && q.options.length;

    container.innerHTML = `
        <article class="card" aria-label="Flashcard">
            <header class="card-header">
                <div class="question-meta">
                    <span class="meta-pill">${q.subject || 'General'}</span>
                    <span class="meta-pill">${q.chapter || 'General'}</span>
                </div>
                <p class="card-progress">Question ${shareIndex + 1} of ${shareQuestions.length}</p>
            </header>
            <section class="question-front">${q.front}</section>
            <div id="mcq-options" class="options-grid" ${hasOptions ? '' : 'hidden'}></div>
            <button class="btn btn-secondary" id="show-answer-btn" ${hasOptions ? 'hidden' : ''}>Show Answer</button>
            <section class="question-back" hidden>${q.back}</section>
            <div id="explanation-box" class="explanation-box" hidden></div>
            <div style="margin-top:1.5rem;">
                <button class="btn btn-primary" id="next-btn" hidden>Next →</button>
            </div>
        </article>
    `;

    document.getElementById('show-answer-btn').onclick = () => revealShare(q);
    document.getElementById('next-btn').onclick = () => { shareIndex++; renderShareQuestion(); };

    if (hasOptions) {
        const mcqContainer = document.getElementById('mcq-options');
        q.options.forEach((opt, idx) => {
            const btn = document.createElement('button');
            btn.className = 'btn-option';
            btn.textContent = opt;
            btn.onclick = () => {
                document.querySelectorAll('#mcq-options .btn-option').forEach(b => b.disabled = true);
                if (idx === q.correct_index) {
                    btn.classList.add('correct');
                    fireConfetti(16);
                } else {
                    btn.classList.add('incorrect');
                    const correctBtn = document.querySelectorAll('#mcq-options .btn-option')[q.correct_index];
                    if (correctBtn) correctBtn.classList.add('correct');
                }
                revealShare(q);
            };
            mcqContainer.appendChild(btn);
        });
    }
}

function revealShare(q) {
    document.querySelector('.question-back').hidden = false;
    document.getElementById('next-btn').hidden = false;
    const box = document.getElementById('explanation-box');
    if (q.explanation) {
        box.innerHTML = `<strong>Why:</strong> ${q.explanation}`;
        box.hidden = false;
    }
}
