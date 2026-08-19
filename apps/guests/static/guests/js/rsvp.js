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

  const form = document.querySelector('[data-rsvp-form]');
  const events = document.querySelector('[data-events-fieldset]');
  if (form && events) {
    const syncEvents = () => {
      const status = form.querySelector("input[name='status']:checked")?.value;
      events.hidden = status === 'not_attending';
      events.querySelectorAll('input').forEach((input) => {
        input.disabled = status === 'not_attending';
      });
    };
    form.querySelectorAll("input[name='status']").forEach((input) => {
      input.addEventListener('change', syncEvents);
    });
    syncEvents();
  }
});
