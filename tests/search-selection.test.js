const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {execFileSync} = require('node:child_process');
const {join, resolve} = require('node:path');
const {JSDOM, VirtualConsole} = require('jsdom');

const root = resolve(__dirname, '..');
const python = join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const html = execFileSync(python, ['-c', `
from tempfile import TemporaryDirectory
from pathlib import Path
from app import create_app
with TemporaryDirectory() as folder:
    app = create_app({'TESTING': True, 'SECRET_KEY': 'ui-test', 'DATABASE': str(Path(folder) / 'test.db'),
                      'DEMO_MODE': True, 'TMDB_API_KEY': '', 'TMDB_READ_ACCESS_TOKEN': '', 'OMDB_API_KEY': ''})
    print(app.test_client().get('/').text)
`], {cwd: root, encoding: 'utf8', env: {...process.env, PYTHONIOENCODING: 'utf-8'}});
const sources = ['interaction-utils.js', 'app.js'].map(name => readFileSync(join(root, 'app/static', name), 'utf8'));
const titles = Array.from({length: 6}, (_, index) => ({key: `demo:${index % 2 ? 'tv' : 'movie'}:${index + 1}`,
  title: `Title ${index + 1}`, year: '2026', media_label: index % 2 ? 'Series' : 'Film', poster: ''}));
const flush = () => new Promise(resolve => setImmediate(resolve));

function setup(t, initial = [], pageHtml = html, settings = {}) {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', error => errors.push(error.message));
  const dom = new JSDOM(pageHtml, {url: 'http://localhost/', runScripts: 'outside-only', virtualConsole, pretendToBeVisual:true});
  t.after(() => dom.window.close());
  const w = dom.window;
  const d = w.document;
  const config = d.getElementById('interaction-config');
  const state = JSON.parse(config.textContent); state.selected = initial.map(item => item.key);
  config.textContent = JSON.stringify(state);
  const motion = {matches: settings.motion ?? true};
  w.matchMedia = () => motion;
  const timers = new Map(); let timerId = 0;
  w.setTimeout = (callback, delay) => { timers.set(++timerId, {callback, delay}); return timerId; };
  w.clearTimeout = id => timers.delete(id);
  // jsdom lacks HTMLFormElement's browser named-property override behavior.
  Object.defineProperty(w.HTMLFormElement.prototype, 'action', {
    get() { return this.elements.namedItem('action') || new URL(this.getAttribute('action'), w.location.href).href; },
    set(value) { this.setAttribute('action', value); }
  });
  const selected = new Map(initial.map(item => [item.key, item]));
  const watchlist = new Set();
  const requests = [];
  let fail = false;
  let release;
  let held = false;
  w.fetch = async (url, options) => {
    const path = new URL(String(url), w.location.href).pathname;
    if (path === '/api/search') return {ok: true, json: async () => ({items: titles})};
    if (path.endsWith('/providers')) return {ok: !settings.providerError,
      json: async () => settings.providerData || {region:'BR',groups:[],link:''}};
    requests.push({path, key: options.body.get('key'), action: options.body.get('action')});
    if (held) await new Promise(resolve => { release = resolve; });
    if (fail) return {ok: false, json: async () => ({message: 'Selection failed'})};
    if (path !== '/selection' && path !== '/favorites' && path !== '/watchlist') {
      return {ok: false, json: async () => ({message: 'Wrong endpoint'})};
    }
    const key = options.body.get('key');
    if (path === '/watchlist') {
      if (options.body.get('action') === 'remove') watchlist.delete(key); else watchlist.add(key);
      return {ok:true,json:async () => ({watchlist:watchlist.has(key)})};
    }
    if (path === '/favorites') return {ok: true, json: async () => ({favorite: true})};
    if (options.body.get('action') === 'remove') selected.delete(key);
    else if (!selected.has(key) && selected.size < 5) selected.set(key, titles.find(item => item.key === key));
    return {ok: true, json: async () => ({selected: [...selected.values()]})};
  };
  sources.forEach(source => w.eval(source));
  const input = d.getElementById('title-query');
  const panel = d.getElementById('suggestions');
  const form = index => d.querySelectorAll('#suggestion-list form[data-selection]')[index];
  return {w, d, input, panel, requests, errors, form, timers, motion,
    tick(delay) { for (const [id,timer] of [...timers]) if (timer.delay === delay) {timers.delete(id); timer.callback();} },
    async search() {
      input.focus(); input.value = 'Title'; input.dispatchEvent(new w.Event('input', {bubbles: true}));
      for (const [id, timer] of timers) if (timer.delay === 300) { timers.delete(id); timer.callback(); }
      await flush();
      assert.equal(panel.hidden, false);
      assert.equal(d.querySelectorAll('.suggestion-row').length, 6);
    },
    fail(value = true) { fail = value; }, hold() { held = true; }, release() { held = false; release(); }
  };
}

for (const pointerType of ['mouse', 'touch']) {
  test(`${pointerType}: selection posts to the endpoint despite input named action and renders the chip`, async t => {
    const ui = setup(t);
    await ui.search();
    const form = ui.form(0);
    const button = form.querySelector('button');
    button.dispatchEvent(new ui.w.PointerEvent('pointerdown', {bubbles: true, pointerType}));
    button.focus(); button.click();
    await flush();
    assert.equal(ui.requests[0].path, '/selection');
    assert.equal(ui.requests[0].action, 'add');
    assert.equal(ui.d.querySelector('#selection-tray .selection-item').dataset.key, titles[0].key);
    assert.equal(ui.d.getElementById('selection-count').textContent, '1 / 5');
    assert.equal(button.getAttribute('aria-pressed'), 'true');
    assert.equal(ui.d.getElementById('live-feedback').hidden, false);
    assert.deepEqual(ui.errors, []);
  });
}

test('focus movement inside the dropdown and indeterminate mobile blur do not close it', async t => {
  const ui = setup(t);
  await ui.search();
  const button = ui.form(0).querySelector('button');
  ui.input.dispatchEvent(new ui.w.FocusEvent('focusout', {bubbles: true, relatedTarget: button}));
  await flush();
  assert.equal(ui.panel.hidden, false);
  ui.input.blur();
  await flush();
  assert.equal(ui.panel.hidden, false);
  button.click(); await flush();
  assert.equal(ui.d.querySelectorAll('#selection-tray .selection-item').length, 1);
});

test('pending selection retains keyboard focus and ignores repeated activation', async t => {
  const ui = setup(t);
  await ui.search(); ui.hold();
  ui.input.dispatchEvent(new ui.w.KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true}));
  ui.d.activeElement.dispatchEvent(new ui.w.KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true}));
  const button = ui.form(0).querySelector('button');
  assert.equal(ui.d.activeElement, button);
  ui.form(0).requestSubmit(button); await flush();
  assert.equal(button.disabled, false);
  assert.equal(button.getAttribute('aria-disabled'), 'true');
  assert.equal(ui.d.activeElement, button);
  assert.equal(ui.panel.hidden, false);
  ui.form(0).requestSubmit(button); await flush();
  assert.equal(ui.requests.length, 1);
  ui.release(); await flush();
  assert.equal(button.getAttribute('aria-disabled'), 'false');
  assert.equal(button.getAttribute('aria-pressed'), 'true');
});

test('five-title limit, removal, re-selection and favorites remain separate', async t => {
  const ui = setup(t); await ui.search();
  for (let index = 0; index < 5; index += 1) { ui.form(index).querySelector('button').click(); await flush(); }
  assert.equal(ui.d.getElementById('selection-count').textContent, '5 / 5');
  assert.equal(ui.d.getElementById('selection-limit').hidden, false);
  assert.equal(ui.form(5).querySelector('button').disabled, true);
  ui.form(5).querySelector('button').click(); await flush();
  assert.equal(ui.requests.length, 5);
  ui.d.querySelector('#selection-tray button').click(); await flush();
  assert.equal(ui.d.querySelectorAll('#selection-tray .selection-item').length, 4);
  ui.form(0).querySelector('button').click(); await flush();
  assert.equal(ui.d.querySelectorAll('#selection-tray .selection-item').length, 5);
  assert.equal(new Set([...ui.d.querySelectorAll('#selection-tray .selection-item')].map(node => node.dataset.key)).size, 5);
  ui.d.querySelector('#suggestion-list form[data-favorite] button').click(); await flush();
  assert.equal(ui.requests.at(-1).path, '/favorites');
  assert.equal(ui.d.querySelectorAll('#selection-tray .selection-item').length, 5);
  assert.deepEqual(ui.errors, []);
});

test('failed selection leaves state unchanged, shows feedback and permits retry', async t => {
  const ui = setup(t); await ui.search(); ui.fail();
  const button = ui.form(0).querySelector('button');
  button.click(); await flush();
  assert.equal(ui.d.querySelectorAll('#selection-tray .selection-item').length, 0);
  assert.equal(ui.d.getElementById('selection-count').textContent, '0 / 5');
  assert.equal(ui.d.getElementById('live-feedback').textContent, 'Selection failed');
  assert.equal(button.disabled, false);
  assert.equal(button.getAttribute('aria-disabled'), 'false');
  ui.fail(false); button.click(); await flush();
  assert.equal(ui.requests.length, 2);
  assert.equal(ui.d.querySelectorAll('#selection-tray .selection-item').length, 1);
  assert.equal(ui.d.getElementById('selection-count').textContent, '1 / 5');
  assert.deepEqual(ui.errors, []);
});

test('outside pointer, Tab out and Escape still close the dropdown', async t => {
  const ui = setup(t); await ui.search();
  ui.d.querySelector('main').dispatchEvent(new ui.w.PointerEvent('pointerdown', {bubbles: true}));
  assert.equal(ui.panel.hidden, true);
  await ui.search();
  ui.d.querySelector('.profile-link').focus(); await flush();
  assert.equal(ui.panel.hidden, true);
  await ui.search();
  ui.input.dispatchEvent(new ui.w.KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  assert.equal(ui.panel.hidden, true);
});

test('single recommendation list keeps all relevant scores and filters', t => {
  const resultsHtml = execFileSync(python, ['-c', `
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from app import create_app
from app.models import Genre, Movie, TVSeries, Recommendation
with TemporaryDirectory() as folder:
    app = create_app({'TESTING': True, 'SECRET_KEY': 'ui-test', 'DATABASE': str(Path(folder) / 'test.db'),
                      'DEMO_MODE': True, 'TMDB_API_KEY': '', 'TMDB_READ_ACCESS_TOKEN': '', 'OMDB_API_KEY': ''})
    client = app.test_client()
    client.get('/')
    with client.session_transaction() as session:
        token = session['csrf_token']
    client.post('/selection', data={'key':'demo:movie:1','csrf_token':token})
    rows = [Recommendation(Movie(101,'Strong',genres=[Genre(18,'Drama')]),85,{'relevant_evidence':1},[]),
            Recommendation(TVSeries(102,'Alternative',genres=[Genre(878,'Sci-fi')]),75,{'relevant_evidence':1},[]),
            Recommendation(Movie(103,'Closest',genres=[Genre(18,'Drama')]),64,{'relevant_evidence':1},[])]
    with patch.object(app.extensions['cinovelle']['engine'],'discover',return_value=rows):
        print(client.post('/recommendations',data={'csrf_token':token}).text)
`], {cwd: root, encoding: 'utf8', env: {...process.env, PYTHONIOENCODING: 'utf-8'}});
  const ui = setup(t, [], resultsHtml);
  const type = ui.d.getElementById('result-type');
  const genre = ui.d.getElementById('result-genre');
  const count = ui.d.getElementById('result-count');
  assert.equal(count.textContent, '3');
  assert.ok(ui.d.querySelector('[data-key="demo:movie:103"] .match-badge').textContent.includes('64%'));
  type.value = 'movie'; type.dispatchEvent(new ui.w.Event('change'));
  assert.equal(count.textContent, '2');
  assert.equal(ui.d.querySelector('[data-key="demo:movie:103"]').hidden, false);
  assert.equal(ui.d.querySelector('[data-key="demo:tv:102"]').hidden, true);
  genre.value = '878'; genre.dispatchEvent(new ui.w.Event('change'));
  assert.equal(count.textContent, '0');
  assert.equal(ui.d.getElementById('filter-empty').hidden, false);
  type.value = 'tv'; type.dispatchEvent(new ui.w.Event('change'));
  assert.equal(count.textContent, '1');
  assert.equal(ui.d.getElementById('filter-empty').hidden, true);
  assert.deepEqual(ui.errors, []);
});

test('hero rotates after six seconds and pauses, preloads and cleans up timers', t => {
  const ui=setup(t,[],html,{motion:false});
  const hero=ui.d.querySelector('[data-hero]'); const slides=[...hero.querySelectorAll('.hero-slide')];
  const running=()=>[...ui.timers.values()].filter(timer=>timer.delay===6000).length;
  assert.ok(slides.length>=5); assert.equal(running(),1);
  assert.ok(slides.slice(2).some(slide=>slide.querySelector('img[data-src]')));
  assert.notEqual(slides[2].querySelector('img').style.visibility,'hidden');
  ui.tick(6000); assert.equal(slides[1].getAttribute('aria-hidden'),'false'); assert.equal(running(),1);
  assert.equal(slides[0].hasAttribute('inert'),true);
  hero.querySelector('[data-hero-next]').click(); assert.equal(running(),0);
  hero.querySelector('[data-hero-index="4"]').click(); assert.equal(slides[4].getAttribute('aria-hidden'),'false');
  hero.querySelector('[data-hero-pause]').click(); assert.equal(running(),1);
  hero.dispatchEvent(new ui.w.PointerEvent('pointerenter')); assert.equal(running(),0);
  hero.dispatchEvent(new ui.w.PointerEvent('pointerleave')); assert.equal(running(),1);
  hero.querySelector('.is-active a').focus(); assert.equal(running(),0);
  ui.input.focus(); assert.equal(running(),1);
  ui.w.dispatchEvent(new ui.w.Event('pagehide')); assert.equal(running(),0);
  ui.w.dispatchEvent(new ui.w.Event('pageshow')); assert.equal(running(),1);
  assert.deepEqual(ui.errors,[]);
});

test('hero reduced motion disables autoplay but preserves navigation', t=>{
  const ui=setup(t); const hero=ui.d.querySelector('[data-hero]');
  assert.equal([...ui.timers.values()].filter(timer=>timer.delay===6000).length,0);
  hero.querySelector('[data-hero-next]').click();
  assert.equal(hero.querySelectorAll('.hero-slide')[1].getAttribute('aria-hidden'),'false');
  assert.equal(hero.querySelector('[data-hero-pause]').disabled,true);
});

test('watchlist updates every matching card independently and survives failed removal',async t=>{
  const ui=setup(t); const form=ui.d.querySelector('form[data-watchlist]'); const key=form.elements.key.value;
  form.querySelector('button').click(); await flush();
  assert.equal(ui.requests[0].path,'/watchlist');
  ui.d.querySelectorAll('form[data-watchlist]').forEach(other=>{
    if(other.elements.key.value===key) assert.equal(other.querySelector('button').getAttribute('aria-pressed'),'true');
  });
  assert.equal(ui.d.getElementById('selection-count').textContent,'0 / 5');
  assert.equal(ui.d.querySelector('form[data-favorite] button').getAttribute('aria-pressed'),'false');
  await ui.search();
  assert.equal(ui.d.querySelector('#suggestion-list form[data-watchlist] button').getAttribute('aria-pressed'),'true');
  ui.fail();form.querySelector('button').click();await flush();
  assert.equal(form.querySelector('button').getAttribute('aria-pressed'),'true');
  ui.fail(false);form.querySelector('button').click();await flush();
  assert.equal(form.querySelector('button').getAttribute('aria-pressed'),'false');
  assert.deepEqual(ui.errors,[]);
});

const detailsHtml=execFileSync(python,['-c',`
from tempfile import TemporaryDirectory
from pathlib import Path
from app import create_app
with TemporaryDirectory() as folder:
 app=create_app({'TESTING':True,'SECRET_KEY':'ui-test','DATABASE':str(Path(folder)/'test.db'),
                 'DEMO_MODE':True,'TMDB_API_KEY':'','TMDB_READ_ACCESS_TOKEN':'','OMDB_API_KEY':''})
 print(app.test_client().get('/title/demo:movie:1').text)
`],{cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'}});

test('watch providers render names, official options and JustWatch credit',async t=>{
 const ui=setup(t,[],detailsHtml,{providerData:{region:'BR',groups:[{kind:'flatrate',providers:[{name:'Example provider',logo:''}]}],link:'https://www.themoviedb.org/movie/1/watch?locale=BR'}});
 const section=ui.d.querySelector('[data-providers-url]');
 assert.equal(section.getAttribute('aria-busy'),'true');await flush();
 assert.equal(section.getAttribute('aria-busy'),'false');
 assert.ok(section.textContent.includes('Example provider'));
 assert.ok(section.textContent.includes('JustWatch'));
 assert.equal(section.querySelector('.provider-groups a').href,'https://www.themoviedb.org/movie/1/watch?locale=BR');
 assert.deepEqual(ui.errors,[]);
});

test('watch provider failure shows retry and empty BR result stays explicit',async t=>{
 const settings={providerError:true};const ui=setup(t,[],detailsHtml,settings);
 const section=ui.d.querySelector('[data-providers-url]');await flush();
 const retry=section.querySelector('.provider-retry');assert.equal(retry.hidden,false);
 settings.providerError=false;retry.click();await flush();
 assert.equal(retry.hidden,true);
 assert.ok(section.querySelector('.provider-status').textContent.includes('Brasil'));
 assert.equal(section.getAttribute('aria-busy'),'false');
});
