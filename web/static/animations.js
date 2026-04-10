/**
 * QuestLog — Celebration Animations (Modern Chronicle)
 *
 * Pure CSS keyframes + vanilla JS particle system.
 * Hooks into HTMX lifecycle via htmx:afterSettle and custom response headers.
 */

// ── Particle burst (quest done, pomo forge) ─────────────────────────────

function burstParticles(cx, cy, {
  count = 14,
  colors = ['#d4943a', '#f5d78e', '#95482b', '#7a9e7e'],
  spread = 80,
  duration = 600,
} = {}) {
  for (let i = 0; i < count; i++) {
    const dot = document.createElement('div');
    const size = 4 + Math.random() * 4;
    const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.5;
    const dist = 40 + Math.random() * spread;
    const tx = Math.cos(angle) * dist;
    const ty = Math.sin(angle) * dist - 20;

    dot.style.cssText = `
      position:fixed; left:${cx}px; top:${cy}px;
      width:${size}px; height:${size}px;
      border-radius:${Math.random() > 0.5 ? '50%' : '2px'};
      background:${colors[i % colors.length]};
      pointer-events:none; z-index:9999;
      opacity:1;
      transition: transform ${duration}ms cubic-bezier(0.4, 0, 0.2, 1),
                  opacity ${duration}ms ease-out;
    `;
    document.body.appendChild(dot);

    // Force layout before applying transform
    dot.offsetHeight;
    dot.style.transform = `translate(${tx}px, ${ty}px) scale(0.3)`;
    dot.style.opacity = '0';

    setTimeout(() => dot.remove(), duration + 50);
  }
}

// ── Quest done celebration ──────────────────────────────────────────────

function celebrateDone(cardEl) {
  if (!cardEl) return;
  const rect = cardEl.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;

  // Pulse the card
  cardEl.style.transition = 'transform 400ms cubic-bezier(0.4, 0, 0.2, 1), box-shadow 400ms ease-out';
  cardEl.style.transform = 'scale(1.04)';
  cardEl.style.boxShadow = '0 0 24px rgba(212, 148, 58, 0.4)';
  setTimeout(() => {
    cardEl.style.transform = '';
    cardEl.style.boxShadow = '';
  }, 400);

  // Particles
  burstParticles(cx, cy, {
    count: 16,
    colors: ['#d4943a', '#f5d78e', '#95482b', '#7a9e7e'],
    spread: 90,
    duration: 700,
  });
}

// ── Pomo forge flash ────────────────────────────────────────────────────

function flashEdges(color, duration) {
  const flash = document.createElement('div');
  flash.style.cssText = `
    position:fixed; inset:0; z-index:9998; pointer-events:none;
    box-shadow: inset 0 0 80px 20px ${color};
    opacity:1;
    transition: opacity ${duration}ms cubic-bezier(0.4, 0, 0.2, 1);
  `;
  document.body.appendChild(flash);
  flash.offsetHeight;
  flash.style.opacity = '0';
  setTimeout(() => flash.remove(), duration + 50);
}

function celebratePomoComplete() {
  flashEdges('rgba(212, 148, 58, 0.3)', 500);
}

function celebrateBerserker() {
  flashEdges('rgba(245, 215, 142, 0.45)', 200);
  setTimeout(() => flashEdges('rgba(245, 215, 142, 0.25)', 200), 100);
}

// ── Trophy earned celebration ────────────────────────────────────────────

function celebrateTrophyEarned() {
  // Find trophy cards and shimmer the most recent one
  const trophyCards = document.querySelectorAll('.trophy-card:not(.trophy-card--locked)');
  if (trophyCards.length > 0) {
    const card = trophyCards[trophyCards.length - 1];
    const rect = card.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;

    // Scale-up pulse
    card.style.transition = 'transform 500ms cubic-bezier(0.4, 0, 0.2, 1), box-shadow 500ms ease-out';
    card.style.transform = 'scale(1.06)';
    card.style.boxShadow = '0 0 32px rgba(212, 148, 58, 0.4)';
    setTimeout(() => {
      card.style.transform = '';
      card.style.boxShadow = '';
    }, 500);

    // Shimmer sweep via class
    card.classList.add('shimmer-sweep');
    setTimeout(() => card.classList.remove('shimmer-sweep'), 800);

    // Gold particles
    burstParticles(cx, cy, {
      count: 12,
      colors: ['#d4943a', '#f5d78e', '#95482b'],
      spread: 70,
      duration: 600,
    });
  }

  // Edge flash
  flashEdges('rgba(212, 148, 58, 0.2)', 400);
}

// ── Inscribe zap ───────────────────────────────────────────────────────

document.addEventListener('submit', function(e) {
  const btn = e.target.querySelector('.btn--zap');
  if (!btn) return;
  btn.classList.remove('is-zapping');
  btn.offsetHeight; // force reflow to restart animation
  btn.classList.add('is-zapping');
  setTimeout(function() { btn.classList.remove('is-zapping'); }, 450);
});

// ── HTMX integration ───────────────────────────────────────────────────

document.body.addEventListener('htmx:afterSettle', function(e) {
  // Stagger-animate new elements
  const els = e.detail.elt.querySelectorAll('[data-animate-in]');
  els.forEach(function(el, i) {
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    setTimeout(function() {
      el.style.transition = 'opacity 300ms cubic-bezier(0.4, 0, 0.2, 1), transform 300ms cubic-bezier(0.4, 0, 0.2, 1)';
      el.style.opacity = '1';
      el.style.transform = 'translateY(0)';
    }, i * 30);
  });
});

// Listen for custom animation triggers via HX-Trigger response header
document.body.addEventListener('quest-done', function(e) {
  // Find the card that just moved to done
  const doneCards = document.querySelectorAll('.quest-card[data-status="done"]');
  if (doneCards.length > 0) {
    celebrateDone(doneCards[doneCards.length - 1]);
  }
});

document.body.addEventListener('pomo-complete', function() {
  celebratePomoComplete();
});

document.body.addEventListener('pomo-berserker', function() {
  celebrateBerserker();
});

document.body.addEventListener('trophy-earned', function() {
  celebrateTrophyEarned();
});
