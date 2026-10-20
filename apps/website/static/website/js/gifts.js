(() => {
  document.querySelectorAll('[data-copy-button]').forEach((button) => {
    const value = button.parentElement?.querySelector('[data-copy-value]')?.dataset.copyValue;
    if (!value || !navigator.clipboard) {
      button.hidden = true;
      return;
    }
    button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(value);
        const originalLabel = button.textContent;
        button.textContent = button.dataset.copySuccess;
        window.setTimeout(() => { button.textContent = originalLabel; }, 1800);
      } catch (_error) {
        button.hidden = true;
      }
    });
  });
})();
