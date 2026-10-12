(() => {
  const normalize = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
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
  const search = document.querySelector('#seating-search');
  const filters = document.querySelector('[data-group-filters]');
  const filterStatus = document.querySelector('[data-filter-status]');
  const applyFilters = () => {
    const query = normalize(search?.value || '');
    const groups = new Set([...document.querySelectorAll('[data-group-filter]:checked')].map((input) => input.value));
    let visible = 0;
    let cleared = 0;
    document.querySelectorAll('[data-search]').forEach((row) => {
      row.hidden = !normalize(row.dataset.search).includes(query) || !groups.has(row.dataset.group);
      const checkbox = row.querySelector('[name="guest_ids"]');
      if (row.hidden && checkbox.checked) {
        checkbox.checked = false;
        cleared += 1;
      }
      if (!row.hidden) visible += 1;
    });
    filterStatus.textContent = `${visible} convive(s) affiché(s).` +
      (cleared ? ` ${cleared} sélection(s) masquée(s) décochée(s).` : '');
    updateSelection();
  };
  if (filters && filterStatus) {
    filters.hidden = false;
    filterStatus.hidden = false;
    filters.addEventListener('change', applyFilters);
    search?.addEventListener('input', applyFilters);
    applyFilters();
  }
  let saving = false;
  const submitAssignment = async (data) => {
    if (saving) return;
    saving = true;
    const feedback = document.querySelector('#seating-feedback');
    feedback.textContent = 'Enregistrement…';
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
  };
  document.querySelectorAll('[data-seating-form]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (form === selectionForm && !updateSelection()) return;
      submitAssignment(new FormData(form));
    });
  });

  let dragged = null;
  const targets = [...document.querySelectorAll('[data-drop-table]')];
  const canDrop = (target) => dragged && !saving &&
    target.dataset.dropTable !== dragged.dataset.sourceTable && Number(target.dataset.remaining) > 0;
  const resetDrag = () => {
    dragged?.classList.remove('seating-dragging');
    dragged = null;
    targets.forEach((target) => target.classList.remove('seating-drop-ready', 'seating-drop-over', 'seating-drop-full'));
  };
  document.querySelectorAll('[data-drag-guest]').forEach((row) => {
    row.addEventListener('dragstart', (event) => {
      if (saving || event.target.closest('input, select, button, a')) {
        event.preventDefault();
        return;
      }
      dragged = row;
      row.classList.add('seating-dragging');
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', row.dataset.dragGuest);
      targets.forEach((target) => {
        if (target.dataset.dropTable !== row.dataset.sourceTable) {
          target.classList.add(canDrop(target) ? 'seating-drop-ready' : 'seating-drop-full');
        }
      });
      document.querySelector('#seating-feedback').textContent = 'Déposez ce convive sur une table disposant d’une place libre.';
    });
    row.addEventListener('dragend', resetDrag);
  });
  targets.forEach((target) => {
    target.addEventListener('dragover', (event) => {
      if (!canDrop(target)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      target.classList.add('seating-drop-over');
    });
    target.addEventListener('dragleave', (event) => {
      if (!target.contains(event.relatedTarget)) target.classList.remove('seating-drop-over');
    });
    target.addEventListener('drop', (event) => {
      if (!dragged) return;
      event.preventDefault();
      if (!canDrop(target)) {
        document.querySelector('#seating-feedback').textContent = 'Choisissez une autre table avec une place libre.';
        resetDrag();
        return;
      }
      const data = new FormData();
      data.set('csrfmiddlewaretoken', document.querySelector('[name="csrfmiddlewaretoken"]').value);
      data.set('action', 'assign');
      data.set('guest_ids', dragged.dataset.dragGuest);
      data.set('table_id', target.dataset.dropTable);
      resetDrag();
      submitAssignment(data);
    });
  });
})();
