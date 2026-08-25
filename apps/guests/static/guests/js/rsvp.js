document.addEventListener('DOMContentLoaded', () => {
  const countdown = document.querySelector('[data-countdown]');
  if (countdown) {
    const deadline = new Date(countdown.dataset.deadline).getTime();
    const renderCountdown = () => {
      const remaining = Math.max(0, deadline - Date.now());
      const totalSeconds = Math.floor(remaining / 1000);
      const values = {
        days: Math.floor(totalSeconds / 86400),
        hours: Math.floor((totalSeconds % 86400) / 3600),
        minutes: Math.floor((totalSeconds % 3600) / 60),
        seconds: totalSeconds % 60,
      };
      Object.entries(values).forEach(([key, value]) => {
        const target = countdown.querySelector(`[data-${key}]`);
        if (target) target.textContent = String(value).padStart(2, '0');
      });
    };
    renderCountdown();
    window.setInterval(renderCountdown, 1000);
  }

  const syncRsvpVisibility = () => {
    const form = document.querySelector('[data-rsvp-form]');
    const events = form?.querySelector('[data-events-fieldset]');
    const decline = form?.querySelector('[data-decline-fieldset]');
    if (!form || !events || !decline) return;
    const syncEvents = () => {
      const status = form.querySelector("input[name='status']:checked")?.value;
      events.hidden = status === 'not_attending';
      events.querySelectorAll('input').forEach((input) => {
        input.disabled = status === 'not_attending';
      });
      decline.hidden = status !== 'not_attending';
      decline.querySelectorAll('input, select, textarea').forEach((input) => {
        input.disabled = status !== 'not_attending';
      });
    };
    form.querySelectorAll("input[name='status']").forEach((input) => {
      input.addEventListener('change', syncEvents);
    });
    syncEvents();
  };

  const syncCompanionAttendance = () => {
    document.querySelectorAll('[data-companion-attendance-form]').forEach((form) => {
      const sync = () => {
        const custom = form.querySelector("input[name='attendance_mode']:checked")?.value === 'custom';
        form.querySelectorAll('[data-custom-attendance-field]').forEach((field) => {
          field.hidden = !custom;
          field.querySelectorAll('input').forEach((input) => { input.disabled = !custom; });
        });
      };
      form.querySelectorAll("input[name='attendance_mode']").forEach((input) => input.addEventListener('change', sync));
      sync();
    });
  };

  const feedback = document.querySelector('[data-async-feedback]');
  let feedbackTimer;
  const dismissFeedback = () => {
    window.clearTimeout(feedbackTimer);
    if (!feedback) return;
    feedback.hidden = true;
    feedback.replaceChildren();
  };
  const announce = (message, success) => {
    if (!feedback) return;
    window.clearTimeout(feedbackTimer);
    feedback.hidden = false;
    const notice = document.createElement('div');
    notice.className = `message async-toast message-${success ? 'success' : 'error'}`;
    notice.setAttribute('role', success ? 'status' : 'alert');
    const copy = document.createElement('span');
    copy.textContent = message;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'async-toast-close';
    close.setAttribute('aria-label', 'Fermer la notification');
    close.textContent = '×';
    close.addEventListener('click', dismissFeedback);
    notice.append(copy, close);
    feedback.replaceChildren(notice);
    feedbackTimer = window.setTimeout(dismissFeedback, success ? 6000 : 10000);
  };

  const replaceFragments = (fragments) => {
    const scrollPosition = { left: window.scrollX, top: window.scrollY };
    Object.entries(fragments || {}).forEach(([name, html]) => {
      const current = document.querySelector(`[data-dashboard-component='${name}']`);
      if (!current) return;
      const template = document.createElement('template');
      template.innerHTML = html.trim();
      const replacement = template.content.firstElementChild;
      if (replacement) current.replaceWith(replacement);
    });
    syncRsvpVisibility();
    syncCompanionAttendance();
    window.requestAnimationFrame(() => {
      window.scrollTo(scrollPosition.left, scrollPosition.top);
    });
  };

  document.addEventListener('submit', async (event) => {
    const form = event.target.closest('[data-async-form]');
    if (!form || !window.fetch) return;
    event.preventDefault();

    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
    if (form.dataset.submitting === 'true') return;

    const submitButton = event.submitter || form.querySelector("button[type='submit']");
    const originalLabel = submitButton?.textContent;
    form.dataset.submitting = 'true';
    form.setAttribute('aria-busy', 'true');
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = submitButton.dataset.loadingLabel || 'Envoi…';
    }

    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (response.redirected) {
        window.location.assign(response.url);
        return;
      }
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) throw new Error('Réponse serveur inattendue');
      const payload = await response.json();
      replaceFragments(payload.fragments);
      announce(payload.message || (response.ok ? 'Modification enregistrée.' : 'La modification a échoué.'), response.ok && payload.ok);
    } catch (error) {
      announce('La modification n’a pas pu être enregistrée. Vérifiez votre connexion puis réessayez.', false);
    } finally {
      form.dataset.submitting = 'false';
      form.removeAttribute('aria-busy');
      if (submitButton?.isConnected) {
        submitButton.disabled = false;
        submitButton.textContent = originalLabel;
      }
    }
  });

  syncRsvpVisibility();
  syncCompanionAttendance();
});
