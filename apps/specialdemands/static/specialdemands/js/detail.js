document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('response-form');
  const feedback = document.getElementById('response-feedback');
  const finalContent = document.getElementById('final-content');
  const confettiLayer = document.getElementById('confetti-layer');
  const body = document.body;

  if (!form || !feedback || !finalContent) {
    return;
  }

  const guestFirstName = body.dataset.guestFirstName || '';
  const buttons = form.querySelectorAll('.decision-btn');
  const csrfToken =
    form.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

  function setButtonsDisabled(disabled) {
    buttons.forEach((btn) => {
      btn.disabled = disabled;
    });
  }

  function showFeedback(html) {
    feedback.classList.remove('hidden');
    feedback.innerHTML = html;
  }

  function hideFeedback() {
    feedback.classList.add('hidden');
    feedback.innerHTML = '';
  }

  function renderAcceptedLoading() {
    showFeedback(`
      <div class="flex flex-col items-center justify-center gap-4 animate-fade-in">
        <div class="heart-loader">
          <span class="heart">💚</span>
        </div>
        <p class="text-lg text-[var(--green)] font-medium">
          Merci pour ta réponse…
        </p>
      </div>
    `);
  }

  function renderAcceptedSuccess() {
    finalContent.innerHTML = `
      <div id="confetti-layer" class="confetti-layer" aria-hidden="true"></div>
      <div class="text-center animate-fade-in relative z-10">
        <p class="text-2xl font-semibold text-[var(--green)] mb-3">
          Merci ${escapeHtml(guestFirstName)} 💚
        </p>
        <p class="text-gray-700">
          Nous avons bien reçu ton acceptation.
        </p>
      </div>
    `;

    const newConfettiLayer = document.getElementById('confetti-layer');
    launchConfetti(newConfettiLayer, 42);
  }

  function renderDeclinedSuccess() {
    finalContent.innerHTML = `
      <div class="text-center animate-fade-in relative z-10">
        <p class="text-2xl font-semibold text-gray-700 mb-3">
          Merci ${escapeHtml(guestFirstName)}
        </p>
        <p class="text-gray-600">
          Nous avons bien reçu ta réponse.
        </p>
      </div>
    `;
  }

  function renderError() {
    showFeedback(`
      <div class="mt-4 text-red-600 animate-fade-in">
        Une erreur est survenue. Merci de réessayer.
      </div>
    `);
  }

  function escapeHtml(value) {
    return value
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function launchConfetti(layer, count = 36) {
    if (!layer) return;

    const classes = [
      'confetti-1',
      'confetti-2',
      'confetti-3',
      'confetti-4',
      'confetti-5',
    ];
    const sizes = ['small', '', 'large'];
    const shapes = ['', 'circle'];

    layer.innerHTML = '';
    layer.classList.remove('hidden');

    for (let i = 0; i < count; i += 1) {
      const piece = document.createElement('span');
      const left = Math.random() * 100;
      const drift = `${Math.round(Math.random() * 220 - 110)}px`;
      const rotate = `${Math.round(Math.random() * 1080 - 540)}deg`;
      const duration = 2400 + Math.random() * 1800;
      const delay = Math.random() * 400;
      const colorClass = classes[Math.floor(Math.random() * classes.length)];
      const sizeClass = sizes[Math.floor(Math.random() * sizes.length)];
      const shapeClass = shapes[Math.floor(Math.random() * shapes.length)];

      piece.className =
        `confetti-piece ${colorClass} ${sizeClass} ${shapeClass}`.trim();
      piece.style.left = `${left}%`;
      piece.style.animationDuration = `${duration}ms`;
      piece.style.animationDelay = `${delay}ms`;
      piece.style.setProperty('--confetti-x', drift);
      piece.style.setProperty('--confetti-rotate', rotate);

      layer.appendChild(piece);

      setTimeout(
        () => {
          piece.remove();
        },
        duration + delay + 100,
      );
    }

    setTimeout(() => {
      if (layer) {
        layer.innerHTML = '';
      }
    }, 4600);
  }

  async function submitDecision(decision) {
    setButtonsDisabled(true);
    hideFeedback();

    if (decision === 'accepted') {
      renderAcceptedLoading();
    }

    try {
      const response = await fetch(form.action, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest',
          'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
          Accept: 'application/json',
        },
        body: new URLSearchParams({
          decision,
          csrfmiddlewaretoken: csrfToken,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Erreur serveur');
      }

      if (data.status === 'accepted') {
        renderAcceptedSuccess();
      } else if (data.status === 'declined') {
        renderDeclinedSuccess();
      } else {
        throw new Error('Réponse inattendue');
      }
    } catch (error) {
      setButtonsDisabled(false);
      renderError();
    }
  }

  form.addEventListener('click', (event) => {
    const button = event.target.closest("button[type='submit']");
    if (!button) return;

    event.preventDefault();
    submitDecision(button.value);
  });
});
