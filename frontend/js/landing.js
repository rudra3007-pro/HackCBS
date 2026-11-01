/* ============================================================
   CycloSense Landing Page — JavaScript
   Scroll effects, fade-in observer, back-to-top
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
  const nav    = document.getElementById('nav');
  const toTop  = document.getElementById('toTop');
  const menu   = document.getElementById('menu');

  // ── Navbar scroll effect & back-to-top show/hide ─────────────
  const onScroll = () => {
    nav?.classList.toggle('scrolled', window.scrollY > 30);
    toTop?.classList.toggle('show', window.scrollY > 450);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // ── Smooth scroll to top ──────────────────────────────────────
  toTop?.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

  // ── Reveal elements as they enter the viewport ────────────────
  const fadeObserver = new IntersectionObserver((entries, obs) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        obs.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });

  document.querySelectorAll('.fade-in').forEach(el => fadeObserver.observe(el));

  // ── Close mobile menu after selecting a nav link ──────────────
  document.querySelectorAll('#menu .nav-link').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth < 992 && menu?.classList.contains('show')) {
        // Use Bootstrap Collapse API if available
        if (typeof bootstrap !== 'undefined') {
          bootstrap.Collapse.getOrCreateInstance(menu).hide();
        }
      }
    });
  });

  // ── Keep active nav link in sync with visible section ─────────
  const sections  = document.querySelectorAll('header[id], main section[id]');
  const navLinks  = document.querySelectorAll('.cs-nav .nav-link');

  const sectionObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        navLinks.forEach(link => {
          link.classList.toggle('active', link.getAttribute('href') === `#${entry.target.id}`);
        });
      }
    });
  }, { rootMargin: '-35% 0px -55% 0px' });

  sections.forEach(section => sectionObserver.observe(section));
});

