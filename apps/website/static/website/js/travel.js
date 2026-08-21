(() => {
  const planner = document.querySelector('[data-route-planner]');
  if (planner) {
    const addressField = planner.querySelector('[data-address-field]');
    const addressInput = planner.querySelector('[data-origin-address]');
    const originKinds = [...planner.querySelectorAll('input[name="origin-kind"]')];
    const routeLinks = [...planner.querySelectorAll('[data-route-link]')];

    const updateOrigin = () => {
      const usesAddress = planner.querySelector('input[name="origin-kind"]:checked').value === 'address';
      addressField.hidden = !usesAddress;
      if (usesAddress) addressInput.focus({ preventScroll: true });
      updateLinks();
    };
    const updateLinks = () => {
      const usesAddress = planner.querySelector('input[name="origin-kind"]:checked').value === 'address';
      const mode = planner.querySelector('input[name="travel-mode"]:checked').value;
      routeLinks.forEach((link) => {
        const url = new URL('https://www.google.com/maps/dir/');
        url.searchParams.set('api', '1');
        if (usesAddress && addressInput.value.trim()) url.searchParams.set('origin', addressInput.value.trim());
        url.searchParams.set('destination', link.dataset.destination);
        url.searchParams.set('travelmode', mode);
        link.href = url.toString();
      });
    };
    originKinds.forEach((input) => input.addEventListener('change', updateOrigin));
    planner.querySelectorAll('input[name="travel-mode"]').forEach((input) => input.addEventListener('change', updateLinks));
    addressInput.addEventListener('input', updateLinks);
    updateLinks();
  }

  const map = document.querySelector('[data-place-map]');
  if (map) {
    const frame = map.querySelector('[data-map-frame] iframe');
    map.querySelectorAll('[data-place-button]').forEach((button) => {
      button.addEventListener('click', () => {
        map.querySelectorAll('[data-place-button]').forEach((item) => item.removeAttribute('aria-current'));
        button.setAttribute('aria-current', 'true');
        if (frame && button.dataset.embedUrl) {
          frame.title = `Carte de ${button.querySelector('strong').textContent}`;
          frame.src = button.dataset.embedUrl;
        }
      });
    });
  }

  const recommendation = document.querySelector('[data-recommendation]');
  if (recommendation) {
    const title = recommendation.querySelector('[data-recommendation-title]');
    const copy = recommendation.querySelector('[data-recommendation-copy]');
    const updateRecommendation = () => {
      const codes = [...recommendation.querySelectorAll('[data-event-choice]:checked')].map((input) => input.value);
      const priority = recommendation.querySelector('input[name="stay-priority"]:checked').value;
      const hasCeremonies = codes.some((code) => ['city_hall', 'church'].includes(code));
      const hasReception = codes.includes('reception');
      if (priority === 'evening' || (hasReception && !hasCeremonies)) {
        title.textContent = 'Privilégiez la proximité de la soirée';
        copy.textContent = 'Ris-Orangis et ses environs limitent le trajet de retour après les festivités.';
      } else if (priority === 'ceremonies' || (hasCeremonies && !hasReception)) {
        title.textContent = 'Privilégiez Puteaux et La Défense';
        copy.textContent = 'Vous serez au plus près des cérémonies et du vin d’honneur.';
      } else {
        title.textContent = 'Recherchez un compromis entre les lieux';
        copy.textContent = 'Vous prévoyez plusieurs étapes : comparez les trajets réels avant de réserver.';
      }
    };
    recommendation.querySelectorAll('input').forEach((input) => input.addEventListener('change', updateRecommendation));
  }
})();
