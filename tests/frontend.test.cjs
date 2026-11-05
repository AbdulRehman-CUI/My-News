// Terminal-only DOM contracts. Uses node's standard library, never a browser.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = name => fs.readFileSync(path.join(__dirname, '../static', name), 'utf8');
const classes = () => {
  const values = new Set();
  return { add: value => values.add(value), remove: value => values.delete(value), contains: value => values.has(value) };
};
const element = top => {
  const properties = new Map();
  return {
    dataset: {}, classList: classes(), properties,
    style: { setProperty: (key, value) => properties.set(key, value), removeProperty: key => properties.delete(key) },
    getBoundingClientRect: () => ({ top }),
  };
};

test('masthead prints once per tab, and remains static if storage is unavailable', () => {
  const storage = new Map();
  const sessionStorage = { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) };
  const run = storageApi => {
    const root = { classList: classes() };
    vm.runInNewContext(source('masthead.js'), { document: { documentElement: root }, sessionStorage: storageApi });
    return root.classList.contains('masthead-enter');
  };
  assert.equal(run(sessionStorage), true);
  assert.equal(run(sessionStorage), false);
  assert.equal(run({ getItem() { throw Error('blocked'); } }), false);
});

function screen({ reduced = false, mobile = false, forms = [], lead = null, reveals = [], fetch, updated } = {}) {
  const listeners = {};
  const media = { matches: reduced, addEventListener: (_, callback) => { listeners.motion = callback; } };
  const observers = [];
  const document = {
    documentElement: { classList: classes() },
    querySelector: selector => selector === '.home-lead' ? lead : null,
    querySelectorAll: selector => ({ '[data-reveal]': reveals, '.story-actions form': forms }[selector] || []),
  };
  const context = {
    document, URL, FormData: class extends Map { constructor(form) { super(Object.entries(form.fields)); } },
    DOMParser: class { parseFromString() { return { getElementById: () => updated }; } },
    fetch, requestAnimationFrame: callback => { callback(); return 1; }, cancelAnimationFrame() {},
    IntersectionObserver: class {
      constructor(callback) { this.callback = callback; this.items = []; observers.push(this); }
      observe(item) { this.items.push(item); }
      unobserve(item) { this.items = this.items.filter(value => value !== item); }
      disconnect() { this.items = []; }
    },
    window: {
      innerHeight: 800, fetch,
      location: { pathname: '/', href: 'http://localhost/' },
      matchMedia: query => query.includes('reduced-motion') ? media : { matches: !mobile, addEventListener() {} },
      addEventListener: (event, callback) => { listeners[event] = callback; },
      removeEventListener: event => { delete listeners[event]; },
    },
  };
  context.window.IntersectionObserver = context.IntersectionObserver;
  vm.runInNewContext(source('screen.js'), context);
  return { observers, listeners, media };
}

test('one observer reveals below-fold groups with capped delays; lead is immediate', () => {
  const lead = element(-1000);
  const reveals = [element(100), ...Array.from({ length: 8 }, () => element(900))];
  const { observers, listeners, media } = screen({ lead, reveals });
  assert.equal(observers.length, 1);
  assert.equal(observers[0].items.length, 8);
  assert.equal(reveals[0].classList.contains('reveal-pending'), false);
  assert.equal(lead.properties.get('--wash-offset'), '12px');
  assert.equal(lead.properties.get('--marks-offset'), '24px');
  observers[0].callback(observers[0].items.map(target => ({ target, isIntersecting: true })));
  assert.equal(reveals[8].properties.get('--reveal-delay'), '150ms');
  assert.equal(observers[0].items.length, 0);
  media.matches = true;
  listeners.motion();
  assert.equal(lead.properties.size, 0);
  assert.equal(listeners.scroll, undefined);
  assert.ok(reveals.every(item => !item.classList.contains('reveal-pending')));
});

test('reduced motion and mobile leave homepage artwork static', () => {
  const lead = element(-200);
  const item = element(900);
  assert.equal(screen({ reduced: true, lead, reveals: [item] }).observers.length, 0);
  assert.equal(lead.properties.size, 0);
  assert.equal(item.classList.contains('reveal-pending'), false);
  assert.equal(screen({ mobile: true, lead }).listeners.scroll, undefined);
});

function action() {
  const attributes = {};
  const button = { name: '', value: '', textContent: 'Save story',
    setAttribute: (key, value) => { attributes[key] = value; }, removeAttribute: key => { delete attributes[key]; } };
  const status = { textContent: '', classList: classes() };
  const busy = {};
  const story = {
    id: 'story-1', getAttribute: key => busy[key], setAttribute: (key, value) => { busy[key] = value; }, removeAttribute: key => { delete busy[key]; },
    querySelector: selector => selector === '.action-status' ? status : null,
    querySelectorAll: selector => selector === 'button' ? [button] : [form],
  };
  let submit;
  const form = {
    fields: { csrf_token: 'token', saved: '1' }, elements: { saved: { value: '1' } }, action: 'http://localhost/paper/save',
    addEventListener: (_, callback) => { submit = callback; }, closest: () => story,
    getAttribute: () => '/paper/save', querySelectorAll: () => [button],
  };
  const freshButton = { textContent: 'Unsave', value: '', hasAttribute: () => true, getAttribute: () => 'true' };
  const fresh = { getAttribute: () => '/paper/save', elements: { saved: { value: '0' } }, querySelectorAll: () => [freshButton] };
  const updated = { querySelectorAll: () => [fresh], querySelector: () => null };
  return { form, button, status, attributes, updated, submit: () => submit({ submitter: button, preventDefault() {} }) };
}

test('Save acknowledges immediately and synchronizes confirmed state in place', async () => {
  const state = action();
  let resolve;
  screen({ forms: [state.form], updated: state.updated, fetch: () => new Promise(done => { resolve = done; }) });
  const result = state.submit();
  assert.match(state.status.textContent, /Updating/);
  assert.equal(state.attributes['aria-disabled'], 'true');
  resolve({ ok: true, url: 'http://localhost/', text: async () => '<article />' });
  await result;
  assert.equal(state.form.elements.saved.value, '0');
  assert.equal(state.button.textContent, 'Unsave');
  assert.equal(state.attributes['aria-pressed'], 'true');
  assert.equal(state.attributes['aria-disabled'], undefined);
  assert.match(state.status.textContent, /up to date/);
});

test('failed actions show an error and preserve the last confirmed saved state', async () => {
  const state = action();
  screen({ forms: [state.form], fetch: async () => ({ ok: false }) });
  await state.submit();
  assert.match(state.status.textContent, /could not be confirmed/);
  assert.equal(state.status.classList.contains('action-error'), true);
  assert.equal(state.form.elements.saved.value, '1');
  assert.equal(state.button.textContent, 'Save story');
  assert.equal(state.attributes['aria-disabled'], undefined);
});
