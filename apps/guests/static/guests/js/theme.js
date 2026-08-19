(() => {
  const root = document.documentElement;
  const savedTheme = localStorage.getItem('wedding-theme');
  if (savedTheme === 'light' || savedTheme === 'dark') {
    root.dataset.theme = savedTheme;
  }

  document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.querySelector('[data-theme-toggle]');
    if (!toggle) return;
    toggle.addEventListener('click', () => {
      const preferredDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const current = root.dataset.theme || (preferredDark ? 'dark' : 'light');
      const next = current === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      localStorage.setItem('wedding-theme', next);
    });
  });
})();
