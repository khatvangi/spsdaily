// SPS Daily Theme Toggle
(function() {
    const themeToggle = document.getElementById('theme-toggle');
    const html = document.documentElement;

    // Check for saved theme preference or default to light
    const savedTheme = localStorage.getItem('sps-theme') || 'light';
    if (savedTheme === 'dark') {
        html.setAttribute('data-theme', 'dark');
        if (themeToggle) themeToggle.innerHTML = '<span class="theme-icon">☀️</span> Light';
    }

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = html.getAttribute('data-theme');
            if (currentTheme === 'dark') {
                html.removeAttribute('data-theme');
                localStorage.setItem('sps-theme', 'light');
                themeToggle.innerHTML = '<span class="theme-icon">🌙</span> Dark';
            } else {
                html.setAttribute('data-theme', 'dark');
                localStorage.setItem('sps-theme', 'dark');
                themeToggle.innerHTML = '<span class="theme-icon">☀️</span> Light';
            }
        });
    }
})();
