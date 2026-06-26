// Web3Legals — main.js

document.addEventListener('DOMContentLoaded', () => {

  // ── Mobile nav toggle ─────────────────────────────────────
  const toggle    = document.querySelector('.nav-toggle');
  const mobileNav = document.querySelector('.mobile-nav');
  const body      = document.body;

  if (toggle && mobileNav) {
    toggle.addEventListener('click', () => {
      const isOpen = mobileNav.classList.toggle('open');
      toggle.classList.toggle('open', isOpen);
      toggle.setAttribute('aria-expanded', String(isOpen));
      // Prevent body scroll when menu open
      body.style.overflow = isOpen ? 'hidden' : '';
    });

    // Close on any mobile nav link click
    mobileNav.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => {
        mobileNav.classList.remove('open');
        toggle.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
        body.style.overflow = '';
      });
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (mobileNav.classList.contains('open') &&
          !mobileNav.contains(e.target) &&
          !toggle.contains(e.target)) {
        mobileNav.classList.remove('open');
        toggle.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
        body.style.overflow = '';
      }
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && mobileNav.classList.contains('open')) {
        mobileNav.classList.remove('open');
        toggle.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
        body.style.overflow = '';
      }
    });
  }

  // ── Active nav link ───────────────────────────────────────
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a, .mobile-nav a').forEach(a => {
    const href = (a.getAttribute('href') || '').split('/').pop();
    if (href === path || (path === '' && href === 'index.html')) {
      a.classList.add('active');
    }
  });

  // ── Navbar style on scroll ────────────────────────────────
  const navbar = document.querySelector('.navbar');
  if (navbar) {
    const onScroll = () => {
      if (window.scrollY > 20) {
        navbar.style.background = 'rgba(10,11,15,.98)';
        navbar.style.boxShadow  = '0 1px 20px rgba(0,0,0,.4)';
      } else {
        navbar.style.background = 'rgba(10,11,15,.92)';
        navbar.style.boxShadow  = 'none';
      }
    };
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  // ── Scroll to top button ──────────────────────────────────
  const scrollBtn = document.querySelector('.scroll-top');
  if (scrollBtn) {
    window.addEventListener('scroll', () => {
      scrollBtn.classList.toggle('visible', window.scrollY > 500);
    }, { passive: true });
    scrollBtn.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // ── Contact form ──────────────────────────────────────────
  const form = document.getElementById('contact-form');
  if (form) {
    form.addEventListener('submit', e => {
      e.preventDefault();
      const btn = form.querySelector('button[type="submit"]');
      const original = btn.textContent;
      btn.textContent = 'Sending…';
      btn.disabled = true;
      setTimeout(() => {
        btn.textContent = '✓ Message Sent!';
        btn.style.background = '#2e7d5e';
        form.reset();
        setTimeout(() => {
          btn.textContent = original;
          btn.style.background = '';
          btn.disabled = false;
        }, 4000);
      }, 1200);
    });
  }

  // ── Scroll-triggered fade-up animations ──────────────────
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'translateY(0)';
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

    document.querySelectorAll('[data-animate]').forEach(el => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(24px)';
      el.style.transition = 'opacity .55s ease, transform .55s ease';
      observer.observe(el);
    });
  }

});
