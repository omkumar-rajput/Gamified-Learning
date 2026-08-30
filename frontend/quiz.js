const API_BASE = '/api';
let dueQuestions = [];
let currentIndex = 0;
let answerRevealed = false;

const stateMap = { 0: "New", 1: "Learning", 2: "Review", 3: "Relearning" };

document.addEventListener('DOMContentLoaded', initQuiz);

async function initQuiz() {
    renderUserSwitcher('user-switcher-slot');
    try {
        const res = await fetch(apiUrl(`${API_BASE}/get_questions`));
        const data = await res.json();
        dueQuestions = data.questions || [];
        currentIndex = 0;
        renderCurrentState();
    } catch (error) {
        console.error("Error fetching questions:", error);
        document.getElementById('quiz-container').innerHTML = `
            <article class="card">
                <h2>Connection Error</h2>
                <p>Could not connect to the backend server. Make sure it is running on port 5000.</p>
            </article>
        `;
    }
}

function renderCurrentState() {
    answerRevealed = false;

    if (dueQuestions.length === 0 || currentIndex >= dueQuestions.length) {
        document.getElementById('quiz-container').innerHTML = `
            <article class="card done-state">
                <h2>All Caught Up! 🎉</h2>
                <p>You have reviewed all your due flashcards for now.</p>
                <a href="learning-path.html" class="btn btn-primary">View Learning Path</a>
                <a href="edit.html" class="btn btn-secondary" style="margin-left:0.5rem;">Manage Questions</a>
            </article>
        `;
        return;
    }

    const q = dueQuestions[currentIndex];

    document.querySelector('.status-badge').textContent = stateMap[q.state] ?? "Review";
    document.querySelector('.question-subject').textContent = q.subject || 'General';
    document.querySelector('.question-chapter').textContent = q.chapter || 'General';
    document.querySelector('.card-progress').textContent =
        `Question ${currentIndex + 1} of ${dueQuestions.length}`;

    document.querySelector('.question-front').textContent = q.front;
    document.querySelector('.question-back').textContent = q.back;

    document.querySelector('.question-back').hidden = true;
    document.querySelector('.rating-controls').hidden = true;
    const explanationBox = document.getElementById('explanation-box');
    explanationBox.hidden = true;
    explanationBox.innerHTML = '';

    const mcqContainer = document.getElementById('mcq-options');
    const showAnswerBtn = document.getElementById('show-answer-btn');

    if (q.options && q.options.length) {
        showAnswerBtn.hidden = true;
        mcqContainer.hidden = false;
        mcqContainer.innerHTML = '';
        q.options.forEach((opt, idx) => {
            const btn = document.createElement('button');
            btn.className = 'btn-option';
            btn.textContent = opt;
            btn.onclick = () => selectOption(idx, btn);
            mcqContainer.appendChild(btn);
        });
    } else {
        showAnswerBtn.hidden = false;
        mcqContainer.hidden = true;
        mcqContainer.innerHTML = '';
    }
}

function selectOption(idx, btnEl) {
    const q = dueQuestions[currentIndex];
    const buttons = document.querySelectorAll('#mcq-options .btn-option');
    buttons.forEach(b => b.disabled = true);

    if (idx === q.correct_index) {
        btnEl.classList.add('correct');
        fireConfetti(16);
    } else {
        btnEl.classList.add('incorrect');
        if (buttons[q.correct_index]) buttons[q.correct_index].classList.add('correct');
    }

    document.querySelector('.question-back').hidden = false;
    document.querySelector('.rating-controls').hidden = false;
    showExplanation(q);
    answerRevealed = true;
}

function showAnswer() {
    const q = dueQuestions[currentIndex];
    document.querySelector('.question-back').hidden = false;
    document.querySelector('.rating-controls').hidden = false;
    showExplanation(q);
    answerRevealed = true;
}

function showExplanation(q) {
    const box = document.getElementById('explanation-box');
    if (q.explanation) {
        box.innerHTML = `<strong>Why:</strong> ${q.explanation}`;
        box.hidden = false;
    } else {
        box.hidden = true;
    }
}

function editCurrentQuestion() {
    if (dueQuestions.length === 0 || currentIndex >= dueQuestions.length) return;
    const q = dueQuestions[currentIndex];
    window.location.href = `edit.html?id=${q.id}`;
}

async function rateCard(rating) {
    if (!answerRevealed) return;

    const q = dueQuestions[currentIndex];
    try {
        const res = await fetch(apiUrl(`${API_BASE}/review`), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: q.id, rating })
        });
        const data = await res.json();
        if (data.xp) showXpToast(data.xp);
    } catch (error) {
        console.error("Error submitting review:", error);
    }

    setTimeout(() => {
        currentIndex++;
        renderCurrentState();
    }, 1500);
}
