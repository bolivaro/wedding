(() => {
  const normalize = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  document.querySelector('#seating-search')?.addEventListener('input', (event) => {
    const query = normalize(event.target.value);
    document.querySelectorAll('[data-search]').forEach((row) => { row.hidden = !normalize(row.dataset.search).includes(query); });
  });
  let saving = false;
  document.querySelectorAll('[data-seating-form]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (saving) return;
      saving = true;
      const feedback = document.querySelector('#seating-feedback');
      feedback.textContent = 'Enregistrement…';
      const data = new FormData(form);
      document.querySelectorAll('[data-seating-form] button').forEach((button) => { button.disabled = true; });
      try {
        const response = await fetch(window.location.href, { method: 'POST', body: data, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Impossible d’enregistrer cette modification.');
        window.location.reload();
      } catch (error) {
        feedback.textContent = error.message || 'Connexion interrompue. Rechargez la page pour vérifier le résultat.';
        saving = false;
        document.querySelectorAll('[data-seating-form] button').forEach((button) => { button.disabled = false; });
        feedback.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    });
  });
})();
