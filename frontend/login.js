document.addEventListener('DOMContentLoaded', () => {
    const themeBtn = document.getElementById('theme-btn');
    themeBtn.textContent = document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙';
    themeBtn.onclick = () => {
        toggleTheme();
        themeBtn.textContent = document.documentElement.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙';
    };

    // If already logged in, skip straight past the login page.
    whoami().then(user => {
        if (user) window.location.href = redirectTarget();
    });

    document.getElementById('login-form').addEventListener('submit', onSubmit);
    document.querySelectorAll('.demo-account-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.getElementById('email').value = btn.dataset.email;
            document.getElementById('password').value = 'demo1234';
            onSubmit(new Event('submit'));
        });
    });
});

function redirectTarget() {
    const params = new URLSearchParams(window.location.search);
    return params.get('next') || 'index.html';
}

async function onSubmit(e) {
    e.preventDefault();
    const submitBtn = document.getElementById('submit-btn');
    const errorBox = document.getElementById('auth-error');
    errorBox.classList.remove('show');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Logging in…';

    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email: document.getElementById('email').value.trim(),
                password: document.getElementById('password').value,
            }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Login failed');
        window.location.href = redirectTarget();
    } catch (err) {
        errorBox.textContent = err.message;
        errorBox.classList.add('show');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Log in';
    }
}
