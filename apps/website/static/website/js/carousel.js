(() => {
  const carousel = document.querySelector('[data-carousel]');
  if (!carousel) return;
  const slides = [...carousel.querySelectorAll('[data-carousel-slide]')];
  const dots = [...carousel.querySelectorAll('[data-carousel-dot]')];
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let index = 0;
  let timer;

  const show = (next) => {
    index = (next + slides.length) % slides.length;
    slides.forEach((slide, position) => { slide.hidden = position !== index; });
    dots.forEach((dot, position) => {
      if (position === index) dot.setAttribute('aria-current', 'true');
      else dot.removeAttribute('aria-current');
    });
  };
  const stop = () => window.clearInterval(timer);
  const start = () => {
    stop();
    if (!reducedMotion && !document.hidden) timer = window.setInterval(() => show(index + 1), 6500);
  };

  carousel.querySelector('[data-carousel-previous]').addEventListener('click', () => { show(index - 1); start(); });
  carousel.querySelector('[data-carousel-next]').addEventListener('click', () => { show(index + 1); start(); });
  dots.forEach((dot) => dot.addEventListener('click', () => { show(Number(dot.dataset.carouselDot)); start(); }));
  carousel.addEventListener('mouseenter', stop);
  carousel.addEventListener('mouseleave', start);
  carousel.addEventListener('focusin', stop);
  carousel.addEventListener('focusout', start);
  document.addEventListener('visibilitychange', start);
  start();
})();
