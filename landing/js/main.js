/**
 * TradingAgents Landing — Scroll animations, progress bar, mobile menu
 */
(function () {
    'use strict';

    // ── Scroll progress bar ──
    const progressBar = document.createElement('div');
    progressBar.style.cssText =
        'position:fixed;top:0;left:0;height:2px;background:linear-gradient(90deg,#22c55e,#14b8a6);z-index:1001;transition:width 0.1s;';
    document.body.appendChild(progressBar);

    // ── Hamburger menu ──
    const hamburger = document.getElementById('hamburger');
    const mobileMenu = document.getElementById('mobileMenu');

    if (hamburger && mobileMenu) {
        hamburger.addEventListener('click', () => {
            hamburger.classList.toggle('active');
            mobileMenu.classList.toggle('open');
            document.body.style.overflow = mobileMenu.classList.contains('open') ? 'hidden' : '';
        });

        mobileMenu.querySelectorAll('.mobile-link').forEach(link => {
            link.addEventListener('click', () => {
                hamburger.classList.remove('active');
                mobileMenu.classList.remove('open');
                document.body.style.overflow = '';
            });
        });
    }

    // ── Nav + progress bar on scroll ──
    const nav = document.getElementById('nav');

    window.addEventListener('scroll', () => {
        const y = window.scrollY;
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        const progress = docHeight > 0 ? (y / docHeight) * 100 : 0;

        nav.classList.toggle('scrolled', y > 60);
        progressBar.style.width = progress + '%';
    }, { passive: true });

    // ── Intersection Observer (reveal on scroll) ──
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                const children = entry.target.querySelectorAll('.step-card, .agent-card, .phase, .trust-card');
                children.forEach((child, i) => {
                    const delay = parseFloat(child.dataset.delay) || 0;
                    setTimeout(() => child.classList.add('visible'), delay * 1000 + i * 80);
                });
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -60px 0px',
    });

    document.querySelectorAll('.steps-grid, .agent-categories, .pipeline, .trust-grid, .sample-card').forEach(el => {
        observer.observe(el);
    });

    // ── Animated counters ──
    const counters = document.querySelectorAll('.stat-num[data-count]');
    const counterObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const el = entry.target;
                const target = parseInt(el.dataset.count);
                let current = 0;
                const step = Math.ceil(target / 40);
                const timer = setInterval(() => {
                    current += step;
                    if (current >= target) {
                        current = target;
                        clearInterval(timer);
                    }
                    el.textContent = current;
                }, 40);
                counterObserver.unobserve(el);
            }
        });
    }, { threshold: 0.5 });

    counters.forEach(c => counterObserver.observe(c));

    // ── Smooth scroll for anchor links ──
    document.querySelectorAll('a[href^="#"]').forEach(link => {
        link.addEventListener('click', (e) => {
            const id = link.getAttribute('href').slice(1);
            const target = document.getElementById(id);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

})();
