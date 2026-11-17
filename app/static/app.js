(() => {
  const config = JSON.parse(document.getElementById('interaction-config').textContent);
  const messages = config.messages;
  const {debounce, mutationQueue, latestSearch} = globalThis.CinovelleUX;
  const enqueue = mutationQueue();
  const selected = new Set(config.selected);
  const favorites = new Set(config.favorites);
  const watchlist = new Set(config.watchlist || []);
  const pending = new Set();
  const input = document.getElementById('title-query');
  const panel = document.getElementById('suggestions');
  const list = document.getElementById('suggestion-list');
  const tray = document.getElementById('selection-tray');
  const mainButton = document.getElementById('recommend-button');
  const shortcut = document.getElementById('recommend-shortcut');
  const live = document.getElementById('live-feedback');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let feedbackTimer;
  let mainVisible = true;
  let generating = false;

  function feedback(message, error = false) {
    clearTimeout(feedbackTimer);
    live.hidden = false;
    live.classList.toggle('is-error', error);
    live.textContent = message;
    feedbackTimer = setTimeout(() => { live.hidden = true; }, 5000);
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function hidden(name, value) {
    const node = element('input');
    node.type = 'hidden'; node.name = name; node.value = value;
    return node;
  }

  function actionForm(item, favorite = false, remove = false) {
    const form = element('form');
    form.method = 'post';
    form.action = favorite ? config.favoriteUrl : config.selectionUrl;
    form.dataset[favorite ? 'favorite' : 'selection'] = '';
    form.append(hidden('csrf_token', config.csrf), hidden('key', item.key), hidden('action', remove ? 'remove' : 'add'));
    const button = element('button', favorite ? 'heart' : 'small-button');
    button.type = 'submit'; form.append(button);
    return form;
  }

  function watchForm(item) {
    const form = element('form'); form.method = 'post'; form.action = config.watchlistUrl;
    form.dataset.watchlist = '';
    form.append(hidden('csrf_token', config.csrf), hidden('key', item.key), hidden('action', 'add'));
    const button = element('button', 'small-button watch-button compact');
    button.type = 'submit'; form.append(button); return form;
  }

  function syncControls() {
    document.querySelectorAll('form[data-selection], form[data-favorite], form[data-watchlist]').forEach(form => {
      const favorite = form.hasAttribute('data-favorite');
      const watching = form.hasAttribute('data-watchlist');
      const active = (watching ? watchlist : favorite ? favorites : selected).has(form.elements.key.value);
      const busy = pending.has(`${watching ? 'watchlist' : favorite ? 'favorite' : 'selection'}:${form.elements.key.value}`);
      const button = form.querySelector('button');
      form.elements.action.value = active ? 'remove' : 'add';
      button.setAttribute('aria-pressed', String(active));
      if (watching) {
        button.disabled = false;
        const label = messages[active ? 'watchlisted' : 'watch_add'];
        button.textContent = button.classList.contains('compact') ? (active ? '▣' : '▯') : label;
        button.setAttribute('aria-label', label); button.title = label;
        button.classList.toggle('is-selected', active);
      } else if (favorite) {
        button.disabled = false;
        button.textContent = active ? '♥' : '♡';
        button.classList.toggle('active', active);
        button.setAttribute('aria-label', messages[active ? 'favorite_remove' : 'favorite_add']);
      } else if (form.closest('.selection-item')) { button.textContent = '×'; button.disabled = false; }
      else {
        button.textContent = active ? `✓ ${messages.selected}` : `+ ${messages.select}`;
        button.classList.toggle('is-selected', active);
        button.disabled = !active && selected.size >= 5;
      }
      button.setAttribute('aria-disabled', String(busy || button.disabled));
      button.setAttribute('aria-busy', String(busy));
    });
    const selectionPending = [...pending].some(key => key.startsWith('selection:'));
    if (mainButton) mainButton.disabled = selected.size === 0 || generating || selectionPending;
    if (shortcut) { shortcut.hidden = selected.size === 0 || mainVisible; shortcut.disabled = generating || selectionPending; }
    const count = document.getElementById('selection-count');
    if (count) count.textContent = `${selected.size} / 5`;
    document.querySelectorAll('.match-count').forEach(node => { node.textContent = `${selected.size}/5`; });
    const limit = document.getElementById('selection-limit');
    if (limit) limit.hidden = selected.size < 5;
  }

  function renderSelection(items, focusKey) {
    selected.clear(); items.forEach(item => selected.add(item.key));
    if (!tray) return;
    const focused = tray.contains(document.activeElement);
    const nextKey = document.activeElement?.closest('.selection-item')?.nextElementSibling?.dataset.key;
    const keys = new Set(items.map(item => item.key));
    tray.querySelector('.selection-empty')?.remove();
    tray.querySelectorAll('.selection-item').forEach(node => {
      if (keys.has(node.dataset.key)) return;
      if (!reduceMotion && node.animate) {
        node.classList.add('removing');
        node.animate([{opacity: 1}, {opacity: 0, transform: 'translateY(-4px)'}], {duration: 180}).finished
          .then(() => node.remove()).catch(() => node.remove());
      } else node.remove();
    });
    items.forEach(item => {
      if ([...tray.children].some(node => node.dataset.key === item.key && !node.classList.contains('removing'))) return;
      const chip = element('div', 'selection-item'); chip.dataset.key = item.key;
      if (item.poster) {
        const image = element('img'); image.src = item.poster; image.alt = ''; image.width = 30; image.height = 45;
        chip.append(image);
      }
      const form = actionForm(item, false, true);
      form.querySelector('button').setAttribute('aria-label', `${messages.remove} ${item.title}`);
      chip.append(element('span', '', item.title), form); tray.append(chip);
    });
    if (!items.length) tray.append(element('p', 'selection-empty', `+ ${messages.selection_hint}`));
    if (focused) {
      const next = [...tray.querySelectorAll('.selection-item:not(.removing)')].find(node => node.dataset.key === (nextKey || focusKey));
      (next?.querySelector('button') || input)?.focus();
    }
  }

  async function mutate(form) {
    // Serialização evita que respostas Set-Cookie concorrentes percam seleções.
    const favorite = form.hasAttribute('data-favorite');
    const watching = form.hasAttribute('data-watchlist');
    const data = new FormData(form);
    const key = data.get('key');
    const active = (watching ? watchlist : favorite ? favorites : selected).has(key);
    data.set('action', active ? 'remove' : 'add');
    const response = await fetch(form.getAttribute('action'), {method: 'POST', headers: {Accept: 'application/json'}, body: data});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || messages.error);
    if (watching) {
      if (payload.watchlist) watchlist.add(key); else watchlist.delete(key);
      feedback(messages[payload.watchlist ? 'watch_saved' : 'watch_removed']);
      if (!payload.watchlist && form.elements.return_to?.value === 'watchlist') {
        const grid = form.closest('.media-grid'); form.closest('.media-card')?.remove();
        const count = document.getElementById('watchlist-count');
        if (count) count.textContent = grid?.querySelectorAll('.media-card').length || 0;
        if (grid && !grid.children.length) grid.append(element('p', 'empty', live.dataset.empty));
      }
    } else if (favorite) {
      if (payload.favorite) favorites.add(key); else favorites.delete(key);
      feedback(messages[payload.favorite ? 'favorite_saved' : 'favorite_deleted']);
      if (form.elements.return_to?.value === 'favorites' && !payload.favorite) {
        const grid = form.closest('.media-grid'); form.closest('.media-card')?.remove();
        const count = document.getElementById('favorite-count');
        if (count) count.textContent = grid?.querySelectorAll('.media-card').length || 0;
        if (grid && !grid.children.length) grid.append(element('p', 'empty', live.dataset.empty));
      }
    } else {
      renderSelection(payload.selected, key);
      feedback(selected.size === 5 && !active ? messages.limit_reached : messages[active ? 'selection_removed' : 'selection_added']);
    }
    syncControls();
  }

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!form.matches('form[data-selection], form[data-favorite], form[data-watchlist]')) return;
    event.preventDefault();
    const button = form.querySelector('button');
    if (button.disabled) return;
    const operation = `${form.hasAttribute('data-watchlist') ? 'watchlist' : form.hasAttribute('data-favorite') ? 'favorite' : 'selection'}:${form.elements.key.value}`;
    if (pending.has(operation)) return;
    pending.add(operation);
    button.classList.add('pending');
    syncControls();
    enqueue(() => mutate(form)).catch(error => feedback(error instanceof TypeError || error instanceof SyntaxError
      ? messages.network_error : error.message || messages.error, true)).finally(() => {
      pending.delete(operation); button.classList.remove('pending'); syncControls();
    });
  });

  function closeSuggestions() {
    if (!panel) return;
    panel.hidden = true; input.setAttribute('aria-expanded', 'false');
  }

  function searchState(busy, message = '') {
    panel.hidden = false; panel.setAttribute('aria-busy', String(busy));
    input.setAttribute('aria-expanded', 'true');
    document.getElementById('search-skeleton').hidden = !busy;
    document.getElementById('suggestion-status').textContent = message;
    list.hidden = busy;
  }

  function renderSuggestions(items) {
    list.replaceChildren();
    items.forEach(item => {
      const row = element('li', 'suggestion-row'); row.dataset.key = item.key;
      const thumb = element('div', 'suggestion-thumb');
      if (item.poster) {
        const image = element('img'); image.src = item.poster; image.alt = ''; image.width = 36; image.height = 54;
        thumb.append(image);
      }
      const copy = element('a', 'suggestion-copy');
      copy.href = `/title/${encodeURIComponent(item.key)}`;
      copy.append(element('strong', '', item.title), element('small', '', `${item.year || '—'} · ${item.media_label}`));
      row.append(thumb, copy, actionForm(item), actionForm(item, true), watchForm(item)); list.append(row);
    });
    searchState(false, items.length ? '' : messages.empty_search); syncControls();
  }

  if (input) {
    const search = latestSearch(window.fetch.bind(window));
    const runSearch = debounce(() => {
      const query = input.value.trim(); if (query.length < 2) return;
      const url = new URL(config.searchUrl, window.location.origin); url.searchParams.set('q', query);
      search.run(url, data => renderSuggestions(data.items), error => searchState(false,
        error instanceof TypeError || error instanceof SyntaxError ? messages.network_error : error.message || messages.error));
    }, 300);
    input.addEventListener('input', () => {
      search.cancel(); runSearch.cancel(); list.replaceChildren();
      if (input.value.trim().length < 2) { closeSuggestions(); return; }
      searchState(true, messages.searching); runSearch();
    });
    document.getElementById('title-search').addEventListener('submit', event => {
      // O formulário GET funciona normalmente sem JavaScript.
      if (input.value.trim().length >= 2) {
        event.preventDefault();
        const first = !panel.hidden && list.querySelector('a');
        if (first && panel.getAttribute('aria-busy') !== 'true') { first.click(); return; }
        search.cancel(); runSearch.cancel(); searchState(true, messages.searching); runSearch();
      }
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' && !panel.hidden && panel.getAttribute('aria-busy') !== 'true') {
        const first = list.querySelector('a, button:not(:disabled)');
        if (first) { event.preventDefault(); first.focus(); }
      } else if (event.key === 'Escape') { search.cancel(); runSearch.cancel(); closeSuggestions(); }
    });
    panel.addEventListener('keydown', event => {
      const buttons = [...list.querySelectorAll('a, button:not(:disabled)')];
      const current = buttons.indexOf(document.activeElement);
      if (event.key === 'Escape') { search.cancel(); runSearch.cancel(); closeSuggestions(); input.focus(); }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault(); const target = current + (event.key === 'ArrowDown' ? 1 : -1);
        if (target < 0) input.focus(); else buttons[Math.min(target, buttons.length - 1)]?.focus();
      }
    });
    document.addEventListener('pointerdown', event => {
      if (!event.target.closest('.search-interaction')) { search.cancel(); runSearch.cancel(); closeSuggestions(); }
    });
    document.querySelector('.search-interaction').addEventListener('focusout', event => {
      if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) {
        search.cancel(); runSearch.cancel(); closeSuggestions();
      }
    });
  }

  if (mainButton && 'IntersectionObserver' in window) {
    new IntersectionObserver(entries => { mainVisible = entries[0].isIntersecting; syncControls(); }).observe(mainButton);
  } else if (mainButton) mainVisible = false;
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => { if (!window.confirm(form.dataset.confirm)) event.preventDefault(); });
  });
  document.querySelectorAll('form[data-loading]').forEach(form => {
    form.addEventListener('submit', event => {
      if (generating || !form.checkValidity()) { event.preventDefault(); return; }
      generating = true; form.setAttribute('aria-busy', 'true');
      document.getElementById('loading').hidden = false; closeSuggestions(); syncControls();
    });
  });
  window.addEventListener('pageshow', () => {
    generating = false; document.getElementById('loading').hidden = true;
    document.querySelectorAll('form[data-loading]').forEach(form => form.removeAttribute('aria-busy')); syncControls();
  });
  document.querySelectorAll('.media-card').forEach((card, index) => card.style.setProperty('--entry-delay', `${Math.min(index, 5) * 35}ms`));
  const imageFallback = img => {
    img.style.visibility = 'hidden';
    const parent = img.parentElement;
    if (parent.matches('.poster, .detail-poster, .suggestion-thumb')) {
      parent.classList.add('image-unavailable'); parent.dataset.title = img.alt || 'cinovelle.';
    }
  };
  document.addEventListener('error', event => { if (event.target.tagName === 'IMG') imageFallback(event.target); }, true);
  document.querySelectorAll('img').forEach(img => { if (img.getAttribute('src') && img.complete && !img.naturalWidth) imageFallback(img); });
  const navbar = document.querySelector('.navbar');
  const scrollNav = () => navbar.classList.toggle('scrolled', window.scrollY > 20);
  window.addEventListener('scroll', scrollNav, {passive: true}); scrollNav();
  document.querySelectorAll('[data-rail]').forEach(button => {
    const rail = document.getElementById(button.dataset.rail);
    button.addEventListener('click', () => rail.scrollBy({left: Number(button.dataset.direction) * rail.clientWidth * .8, behavior: reduceMotion ? 'instant' : 'smooth'}));
    const update = () => { button.disabled = button.dataset.direction === '-1' ? rail.scrollLeft < 2 : rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 2; };
    rail.addEventListener('scroll', update, {passive: true});
    window.addEventListener('resize', update); update();
  });
  const typeFilter = document.getElementById('result-type');
  const genreFilter = document.getElementById('result-genre');
  if (typeFilter && genreFilter) {
    const filterResults = () => {
      let count = 0;
      document.querySelectorAll('.results-grid .media-card').forEach(card => {
        card.hidden = (typeFilter.value !== 'both' && card.dataset.type !== typeFilter.value)
          || (genreFilter.value !== '' && !card.dataset.genres.split(',').includes(genreFilter.value));
        if (!card.hidden) count += 1;
      });
      document.getElementById('result-count').textContent = count;
      document.getElementById('filter-empty').hidden = count !== 0;
    };
    typeFilter.addEventListener('change', filterResults); genreFilter.addEventListener('change', filterResults);
    document.querySelector('.result-filters').addEventListener('submit', event => event.preventDefault());
  }
  const hero = document.querySelector('[data-hero]');
  if (hero) {
    const slides = [...hero.querySelectorAll('.hero-slide')];
    const dots = [...hero.querySelectorAll('[data-hero-index]')];
    const pause = hero.querySelector('[data-hero-pause]');
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let index = 0, timer = null, paused = false, hovered = false, focused = false, active = true;
    const stop = () => { clearTimeout(timer); timer = null; };
    const prepare = next => slides[next]?.querySelectorAll('img[data-src]').forEach(img => {
      img.src = img.dataset.src; img.removeAttribute('data-src');
    });
    const schedule = () => {
      stop();
      if (active && slides.length > 1 && !motion.matches && !paused && !hovered && !focused && !document.hidden) {
        timer = setTimeout(() => { show(index + 1); }, 6000);
      }
      if (pause) {
        pause.disabled = motion.matches;
        pause.textContent = paused || motion.matches ? '▶' : 'Ⅱ';
        pause.setAttribute('aria-label', hero.dataset[paused || motion.matches ? 'play' : 'pause']);
        pause.setAttribute('aria-pressed', String(paused));
      }
    };
    const show = (next, manual = false) => {
      index = (next + slides.length) % slides.length; prepare(index);
      slides.forEach((slide, position) => {
        const current = position === index;
        slide.classList.toggle('is-active', current); slide.setAttribute('aria-hidden', String(!current));
        if (current) slide.removeAttribute('inert'); else slide.setAttribute('inert', '');
        dots[position]?.setAttribute('aria-current', String(current));
      });
      prepare((index + 1) % slides.length);
      if (manual) paused = true;
      schedule();
    };
    hero.querySelector('[data-hero-prev]')?.addEventListener('click', () => show(index - 1, true));
    hero.querySelector('[data-hero-next]')?.addEventListener('click', () => show(index + 1, true));
    dots.forEach(dot => dot.addEventListener('click', () => show(Number(dot.dataset.heroIndex), true)));
    pause?.addEventListener('click', () => { paused = !paused; schedule(); });
    hero.addEventListener('pointerenter', () => { hovered = true; schedule(); });
    hero.addEventListener('pointerleave', () => { hovered = false; schedule(); });
    hero.addEventListener('focusin', () => { focused = true; schedule(); });
    hero.addEventListener('focusout', event => { focused = hero.contains(event.relatedTarget); schedule(); });
    document.addEventListener('visibilitychange', schedule);
    motion.addEventListener?.('change', schedule);
    window.addEventListener('pagehide', () => { active = false; stop(); });
    window.addEventListener('pageshow', () => { active = true; schedule(); });
    prepare((index + 1) % slides.length); schedule();
  }
  const providers = document.querySelector('[data-providers-url]');
  if (providers) {
    const search = latestSearch(window.fetch.bind(window));
    const status = providers.querySelector('.provider-status');
    const groups = providers.querySelector('.provider-groups');
    const retry = providers.querySelector('.provider-retry');
    const load = () => {
      providers.setAttribute('aria-busy', 'true'); status.textContent = messages.loading; retry.hidden = true;
      search.run(providers.dataset.providersUrl, data => {
        groups.replaceChildren();
        data.groups.forEach(group => {
          const section = element('section', 'provider-group');
          section.append(element('h3', '', providers.dataset[group.kind]));
          const list = element('ul', 'provider-list');
          group.providers.forEach(provider => {
            const row = element('li');
            if (provider.logo) {
              const img = element('img'); img.src = provider.logo; img.alt = ''; img.width = 44; img.height = 44;
              img.loading = 'lazy'; row.append(img);
            }
            row.append(element('span', '', provider.name)); list.append(row);
          });
          section.append(list); groups.append(section);
        });
        if (data.link) {
          const link = element('a', 'button', providers.dataset.link); link.href = data.link;
          link.target = '_blank'; link.rel = 'noopener'; groups.append(link);
        }
        status.textContent = data.groups.length ? '' : providers.dataset.empty;
        providers.setAttribute('aria-busy', 'false');
      }, () => {
        status.textContent = providers.dataset.error; retry.hidden = false;
        providers.setAttribute('aria-busy', 'false');
      });
    };
    retry.addEventListener('click', load);
    window.addEventListener('pagehide', () => search.cancel());
    window.addEventListener('pageshow', event => { if (event.persisted) load(); });
    load();
  }
  syncControls();
})();
