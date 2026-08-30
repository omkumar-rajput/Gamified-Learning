const API_BASE = '/api';
let questionCatalog = { subjects: [], chapters_by_subject: {} };

// --- Drag-and-drop logic ---
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileNameEl = document.getElementById('file-name');

document.addEventListener('DOMContentLoaded', initUploadPage);

async function initUploadPage() {
    renderUserSwitcher('user-switcher-slot');
    const subjectInput = document.getElementById('upload-subject');
    subjectInput.addEventListener('input', renderChapterOptions);
    subjectInput.addEventListener('change', renderChapterOptions);

    await fetchCatalog();
}

async function fetchCatalog() {
    try {
        const response = await fetch(`${API_BASE}/catalog`);
        if (!response.ok) return;

        const data = await response.json();
        questionCatalog = {
            subjects: data.subjects || [],
            chapters_by_subject: data.chapters_by_subject || {},
        };
        renderSubjectOptions();
        renderChapterOptions();
    } catch (error) {
        console.error('Error loading catalog:', error);
    }
}

function renderSubjectOptions() {
    const subjectOptions = document.getElementById('upload-subject-options');
    subjectOptions.innerHTML = '';

    questionCatalog.subjects.forEach(subject => {
        const option = document.createElement('option');
        option.value = subject;
        subjectOptions.appendChild(option);
    });
}

function renderChapterOptions() {
    const subject = document.getElementById('upload-subject').value.trim();
    const chapterOptions = document.getElementById('upload-chapter-options');
    chapterOptions.innerHTML = '';

    const chapters = subject && questionCatalog.chapters_by_subject[subject]
        ? questionCatalog.chapters_by_subject[subject]
        : Object.values(questionCatalog.chapters_by_subject).flat();

    [...new Set(chapters)].forEach(chapter => {
        const option = document.createElement('option');
        option.value = chapter;
        chapterOptions.appendChild(option);
    });
}

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });

dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) setFile(file);
});

fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) setFile(fileInput.files[0]);
});

function setFile(file) {
    fileInput._selectedFile = file;
    fileNameEl.textContent = `📄 ${file.name}`;
}

// --- Submit logic ---
async function submitContent() {
    const text = document.getElementById('content-text').value.trim();
    const file = fileInput._selectedFile;
    const subject = document.getElementById('upload-subject').value.trim();
    const chapter = document.getElementById('upload-chapter').value.trim();

    if (!text && !file) {
        showResult('error', 'Please paste some text or upload a file first.');
        return;
    }

    if (!subject || !chapter) {
        showResult('error', 'Please choose a subject and chapter for the generated flashcards.');
        return;
    }

    setLoading(true);
    clearResult();

    try {
        const formData = new FormData();
        formData.append('subject', subject);
        formData.append('chapter', chapter);
        if (text) formData.append('text', text);
        if (file)  formData.append('file', file);

        const response = await fetch(apiUrl(`${API_BASE}/upload_content`), {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const data = await response.json();

        if (data.success) {
            const count = data.generated ?? 0;
            const competencies = [...new Set((data.questions || []).map(q => q.competency).filter(Boolean))];
            const compNote = competencies.length
                ? ` Auto-tagged competencies: ${competencies.join(', ')}.`
                : '';
            const visibilityNote = data.visibility === 'private'
                ? ' This deck is private to you — mint a share link below to hand it to anyone.'
                : ' Added to the shared question bank.';
            const msg = count > 0
                ? `✅ Success! Generated ${count} MCQ${count !== 1 ? 's' : ''}.${compNote}${visibilityNote} <a href="edit.html" style="color:inherit;font-weight:700;">View in Manage →</a>`
                : `✅ Upload received! Questions will be processed shortly.`;
            showResult('success', msg);
            if (count > 0) {
                fireConfetti(24);
                showShareButton((data.questions || []).map(q => q.id));
            }
        } else {
            showResult('error', data.error || 'Upload failed. Please try again.');
        }
    } catch (err) {
        console.error(err);
        showResult('error', 'Could not reach the server. Is the backend running?');
    } finally {
        setLoading(false);
    }
}

function setLoading(loading) {
    const btn    = document.getElementById('submit-btn');
    const label  = document.getElementById('btn-label');
    const spinner = document.getElementById('spinner');
    btn.disabled = loading;
    label.textContent = loading ? 'Uploading...' : 'Generate Flashcards';
    spinner.style.display = loading ? 'block' : 'none';
}

function showResult(type, html) {
    const box = document.getElementById('result-box');
    box.className = `result-box ${type}`;
    box.innerHTML = html;
}

function clearResult() {
    const box = document.getElementById('result-box');
    box.className = 'result-box';
    box.innerHTML = '';
    const shareBox = document.getElementById('share-box');
    if (shareBox) shareBox.remove();
}

// --- Share link ---
function showShareButton(questionIds) {
    const panel = document.querySelector('.upload-panel');
    const shareBox = document.createElement('div');
    shareBox.id = 'share-box';
    shareBox.style.marginTop = '1rem';

    const btn = document.createElement('button');
    btn.className = 'btn btn-secondary';
    btn.textContent = '🔗 Share this deck';
    btn.onclick = async () => {
        btn.disabled = true;
        btn.textContent = 'Creating link…';
        try {
            const res = await fetch(`${API_BASE}/share`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question_ids: questionIds }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Could not create share link');
            const url = `${window.location.origin}${data.url}`;
            shareBox.innerHTML = `
                <div class="masked-key" style="display:flex; gap:0.5rem; align-items:center; justify-content:space-between;">
                    <span id="share-url" style="overflow:auto; white-space:nowrap;">${url}</span>
                    <button class="btn btn-primary btn-sm" id="copy-share-btn" type="button">Copy</button>
                </div>`;
            document.getElementById('copy-share-btn').onclick = () => {
                navigator.clipboard.writeText(url);
                document.getElementById('copy-share-btn').textContent = 'Copied!';
            };
        } catch (err) {
            btn.disabled = false;
            btn.textContent = '🔗 Share this deck';
            showResult('error', err.message);
        }
    };

    shareBox.appendChild(btn);
    panel.appendChild(shareBox);
}
