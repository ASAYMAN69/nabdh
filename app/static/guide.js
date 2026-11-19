// Theme toggle for the documentation page. Kept external for the strict CSP.
const meta = document.querySelector('meta[name="color-scheme"]');
const btn = document.getElementById('theme-toggle');
if (meta && btn) {
  const getSystemScheme = () =>
    window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  btn.addEventListener('click', () => {
    const stored = (() => {
      try {
        const v = localStorage.getItem('color-scheme');
        return v === 'light' || v === 'dark' ? v : null;
      } catch {
        return null;
      }
    })();
    const rendered = stored ?? getSystemScheme();
    const target = rendered === 'dark' ? 'light' : 'dark';
    const system = getSystemScheme();
    try {
      if (target === system) {
        localStorage.removeItem('color-scheme');
        meta.content = 'light dark';
      } else {
        localStorage.setItem('color-scheme', target);
        meta.content = target;
      }
    } catch {
      meta.content = target === system ? 'light dark' : target;
    }
  });
}