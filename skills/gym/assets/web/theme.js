(() => {
  const key = 'gympilot-theme';
  let theme = null;
  try { theme = localStorage.getItem(key); } catch (_error) {}
  if (theme !== 'light' && theme !== 'dark') {
    theme = globalThis.matchMedia?.('(prefers-color-scheme: light)')?.matches ? 'light' : 'dark';
  }
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === 'light' ? '#f5f6fa' : '#08090d';
})();
