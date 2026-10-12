(() => {
  const normalize = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  document.querySelector('#seating-search')?.addEventListener('input', (event) => {
    const query = normalize(event.target.value);
    document.querySelectorAll('[data-search]').forEach((row) => { row.hidden = !normalize(row.dataset.search).includes(query); });
  });
  const selectionForm = document.querySelector('[data-selection-status]')?.closest('form');
  const updateSelection = () => {
    if (!selectionForm) return true;
    const count = selectionForm.querySelectorAll('[name="guest_ids"]:checked').length;
    const select = selectionForm.querySelector('[name="table_id"]');
    select.querySelectorAll('[data-remaining]').forEach((option) => {
      option.disabled = Number(option.dataset.remaining) < Math.max(1, count);
    });
    if (select.selectedOptions[0]?.disabled) select.value = '';
    const valid = count > 0 && count <= 10 && Boolean(select.value);
    selectionForm.querySelector('button[type="submit"]').disabled = !valid;
    const status = selectionForm.querySelector('[data-selection-status]');
    status.textContent = `${count} / 10 convives sélectionnés.`;
    if (count > 10) {
      status.textContent += ' Retirez des convives pour respecter la limite de 10.';
    } else if (count > 0 && ![...select.options].some((option) => option.value && !option.disabled)) {
      status.textContent += ' Aucune table ne dispose de suffisamment de places.';
    } else if (count > 0 && !select.value) {
      status.textContent += ' Choisissez une table avec assez de places.';
    }
    return valid;
  };
  selectionForm?.addEventListener('change', updateSelection);
  updateSelection();
  let saving = false;
  document.querySelectorAll('[data-seating-form]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (saving) return;
      if (form === selectionForm && !updateSelection()) return;
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
        updateSelection();
        feedback.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    });
  });
})();
