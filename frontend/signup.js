document.addEventListener('DOMContentLoaded', () => {
    const themeBtn = document.getElementById('theme-btn');
    themeBtn.textContent = document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙';
    themeBtn.onclick = () => {
        toggleTheme();
        themeBtn.textContent = document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙';
    };

    whoami().then(user => {
        if (user) window.location.href = 'index.html';
    });

    document.getElementById('signup-form').addEventListener('submit', onSubmit);
});

async function onSubmit(e) {
    e.preventDefault();
    const submitBtn = document.getElementById('submit-btn');
    const errorBox = document.getElementById('auth-error');
    errorBox.classList.remove('show');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating account…';

    try {
        const res = await fetch('/api/auth/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: document.getElementById('name').value.trim(),
                email: document.getElementById('email').value.trim(),
                password: document.getElementById('password').value,
            }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Sign up failed');
        window.location.href = 'upload.html';
    } catch (err) {
        errorBox.textContent = err.message;
        errorBox.classList.add('show');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Create account';
    }
}
