// Decorative image failures never obscure the story or its controls.
document.querySelectorAll('[data-story-media]').forEach(frame => {
  const image = frame.querySelector('img');
  const unavailable = () => {
    image.hidden = true;
    frame.classList.add('media-unavailable');
    frame.querySelector('.image-unavailable').hidden = false;
  };
  image.addEventListener('error', unavailable, { once: true });
  if (image.complete && image.naturalWidth === 0) unavailable();
});

const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
const reveals = document.querySelectorAll('[data-reveal]');
let revealObserver;
let scrollFrame = 0;
const lead = document.querySelector('.home-lead');

function updateParallax() {
  scrollFrame = 0;
  // Two slow print layers; text stays in the document's normal flow.
  const distance = Math.max(0, Math.min(240, -lead.getBoundingClientRect().top));
  lead.style.setProperty('--wash-offset', `${distance * 0.05}px`);
  lead.style.setProperty('--marks-offset', `${distance * 0.1}px`);
}

function onScroll() {
  if (!scrollFrame) scrollFrame = requestAnimationFrame(updateParallax);
}

function configureMotion() {
  revealObserver?.disconnect();
  reveals.forEach(item => item.classList.remove('reveal-pending'));
  window.removeEventListener('scroll', onScroll);
  cancelAnimationFrame(scrollFrame);
  scrollFrame = 0;
  lead?.style.removeProperty('--wash-offset');
  lead?.style.removeProperty('--marks-offset');
  if (motionPreference.matches) return;

  if ('IntersectionObserver' in window) {
    revealObserver = new IntersectionObserver(entries => {
      // Cap each visible group at 150 ms, regardless of the length of the feed.
      entries.filter(entry => entry.isIntersecting).forEach((entry, index) => {
        entry.target.style.setProperty('--reveal-delay', `${Math.min(index, 3) * 50}ms`);
        entry.target.classList.remove('reveal-pending');
        revealObserver.unobserve(entry.target);
      });
    }, { threshold: 0.05 });
    reveals.forEach(item => {
      // Never hide content already in view or replay an item already revealed.
      if (!item.dataset.revealed && item.getBoundingClientRect().top > window.innerHeight) {
        item.classList.add('reveal-pending');
        revealObserver.observe(item);
      }
      item.dataset.revealed = 'true';
    });
  }
  if (lead && window.matchMedia('(min-width: 761px)').matches) {
    updateParallax();
    window.addEventListener('scroll', onScroll, { passive: true });
  }
}
configureMotion();
motionPreference.addEventListener('change', configureMotion);
window.matchMedia('(min-width: 761px)').addEventListener('change', configureMotion);
// A restored page must not retain a print entrance from its first visit.
window.addEventListener('pageshow', event => {
  if (event.persisted) document.documentElement.classList.remove('masthead-enter');
});

// Keep native POSTs and CSRF fields as the fallback. Enhance only story actions.
document.querySelectorAll('.story-actions form').forEach(form => {
  form.addEventListener('submit', async event => {
    const button = event.submitter;
    if (!button || !window.fetch) return;
    event.preventDefault();
    const story = form.closest('.story-card');
    if (story.getAttribute('aria-busy') === 'true') return;
    const status = story.querySelector('.action-status');
    const data = new FormData(form);
    if (button.name) data.set(button.name, button.value);
    // One identity per attempt prevents More and Less sharing an old event ID.
    if (data.has('event_id')) {
      data.set('event_id', window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`);
    }
    story.setAttribute('aria-busy', 'true');
    story.querySelectorAll('button').forEach(control => control.setAttribute('aria-disabled', 'true'));
    status.textContent = 'Updating your reading space…';
    status.classList.remove('action-error');
    try {
      let response = await fetch(form.action, { method: 'POST', body: data });
      if (!response.ok || new URL(response.url).pathname === '/profiles') throw new Error('Update failed');
      // Archive actions redirect to Today on the server; retain this edition and scroll position.
      if (new URL(response.url).pathname !== window.location.pathname) response = await fetch(window.location.href);
      if (!response.ok || new URL(response.url).pathname !== window.location.pathname) throw new Error('Refresh failed');
      const updated = new DOMParser().parseFromString(await response.text(), 'text/html').getElementById(story.id);
      const saving = data.has('saved') || ['save', 'unsave'].includes(button.value);
      if (saving && !updated) throw new Error('Saved state unavailable');
      // Synchronize server-rendered state without replacing the focused control.
      if (updated) {
        const freshForms = [...updated.querySelectorAll('.story-actions form')];
        story.querySelectorAll('.story-actions form').forEach(current => {
          const fresh = freshForms.find(candidate => candidate.getAttribute('action') === current.getAttribute('action'));
          if (!fresh) return;
          ['saved', 'completed'].forEach(name => {
            if (current.elements[name]) current.elements[name].value = fresh.elements[name].value;
          });
          current.querySelectorAll('button').forEach((control, index) => {
            const freshButton = fresh.querySelectorAll('button')[index];
            if (freshButton) {
              control.textContent = freshButton.textContent;
              control.value = freshButton.value;
              if (freshButton.hasAttribute('aria-pressed')) control.setAttribute('aria-pressed', freshButton.getAttribute('aria-pressed'));
            }
          });
        });
        const oldBadge = story.querySelector('.read-badge');
        const newBadge = updated.querySelector('.read-badge');
        if (oldBadge && !newBadge) oldBadge.remove();
        if (!oldBadge && newBadge) story.querySelector('.story-kicker').append(newBadge);
      }
      status.textContent = saving ? 'Your saved stories are up to date. ✓'
        : form.action.endsWith('/progress') ? 'Your reading progress is saved. ✓'
        : form.action.endsWith('/visible') ? 'Story marked seen. ✓'
        : 'Your reading preferences are updated. ✓';
    } catch (_) {
      status.textContent = 'Update could not be confirmed. Refresh to check your state before trying again.';
      status.classList.add('action-error');
    } finally {
      story.removeAttribute('aria-busy');
      story.querySelectorAll('button').forEach(control => control.removeAttribute('aria-disabled'));
    }
  });
});

const librarySearch = document.querySelector('.library-search');
librarySearch?.addEventListener('submit', async event => {
  if (!window.fetch) return;
  event.preventDefault();
  const url = new URL(librarySearch.action);
  url.search = new URLSearchParams(new FormData(librarySearch)).toString();
  const status = document.querySelector('.library-results');
  // Submit only; typing never triggers a request or replaces the search field.
  if (librarySearch.getAttribute('aria-busy') === 'true') return;
  librarySearch.setAttribute('aria-busy', 'true');
  status.textContent = 'Searching your reading space…';
  try {
    const response = await fetch(url);
    if (!response.ok || new URL(response.url).pathname !== url.pathname) throw new Error('Search failed');
    const result = new DOMParser().parseFromString(await response.text(), 'text/html');
    document.querySelectorAll('.library-section').forEach((section, index) => {
      section.replaceChildren(...result.querySelectorAll('.library-section')[index].childNodes);
      section.classList.remove('results-updated');
      requestAnimationFrame(() => section.classList.add('results-updated'));
    });
    status.textContent = result.querySelector('.library-results').textContent;
    history.pushState(null, '', url);
  } catch (_) {
    status.textContent = 'Search could not be completed. Please try again.';
  } finally {
    librarySearch.removeAttribute('aria-busy');
  }
});
// History navigation restores the corresponding server-rendered search results.
if (librarySearch) window.addEventListener('popstate', () => window.location.reload());
