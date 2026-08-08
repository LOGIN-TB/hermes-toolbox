import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const views = ['today', 'plan', 'progress', 'settings'].map(name => ({
  dataset: {view: name},
  hidden: false,
}));
const links = ['today', 'plan', 'progress', 'settings'].map(name => ({
  dataset: {target: name},
  classList: {
    active: false,
    toggle(_className, enabled) { this.active = enabled; },
  },
  addEventListener() {},
}));

globalThis.document = {
  documentElement: {lang: 'de'},
  addEventListener() {},
  getElementById() { return {}; },
  querySelectorAll(selector) {
    if (selector === '[data-view]') return views;
    if (selector === 'nav [data-target]') return links;
    return [];
  },
};
Object.defineProperty(globalThis, 'navigator', {value: {}, configurable: true});

const appSource = fs.readFileSync('skills/gym/assets/web/app.js', 'utf8');
vm.runInThisContext(`${appSource}\nglobalThis.__gymPilotTest = { selectView, exerciseCard, setUnits: value => { displayUnits = value; } };`);

__gymPilotTest.selectView('plan');
assert.equal(views.find(view => view.dataset.view === 'plan').hidden, false);
assert.equal(views.find(view => view.dataset.view === 'today').hidden, true);
assert.equal(links.find(link => link.dataset.target === 'plan').classList.active, true);
assert.equal(links.find(link => link.dataset.target === 'today').classList.active, false);

const exercise = {
  name: 'Beinpresse', planned_sets: 3, min_reps: 8, max_reps: 12,
  current_progress: {completed_sets: 1, planned_sets: 3},
  last_sets: [{weight_kg: 87.5, reps: 10, side: '', equipment_alias: 'Beinpresse Studio A'}],
  current_sets: [{weight_kg: 90, reps: 9, side: '', equipment_alias: 'Beinpresse Studio A'}],
};
__gymPilotTest.setUnits('metric');
const metricCard = __gymPilotTest.exerciseCard(exercise, 0, '2026-08-01');
assert.match(metricCard, /Beinpresse Studio A · 87,5 kg × 10/);
assert.match(metricCard, /Beinpresse Studio A · 90 kg × 9/);
assert.match(metricCard, /1\/3/);

__gymPilotTest.setUnits('imperial');
const imperialCard = __gymPilotTest.exerciseCard({...exercise, last_sets: [{weight_kg: 45.359237, reps: 8, side: '', equipment_alias: ''}]}, 0, '2026-08-01');
assert.match(imperialCard, /100 lb × 8/);

let fetchHandler;
let cacheTouched = false;
let fetchOptions;
const swContext = vm.createContext({
  URL,
  location: {origin: 'http://127.0.0.1:8765'},
  fetch: async (_request, options) => { fetchOptions = options; return {ok: true}; },
  caches: {
    async match() { cacheTouched = true; return null; },
    async open() { cacheTouched = true; return {addAll: async () => {}, put: async () => {}}; },
    async keys() { cacheTouched = true; return []; },
    async delete() { cacheTouched = true; return true; },
  },
  self: {
    clients: {claim() {}},
    skipWaiting() {},
    addEventListener(name, handler) { if (name === 'fetch') fetchHandler = handler; },
  },
});
vm.runInContext(fs.readFileSync('skills/gym/assets/web/service-worker.js', 'utf8'), swContext);
assert.equal(typeof fetchHandler, 'function');
let responsePromise;
fetchHandler({
  request: {url: 'http://127.0.0.1:8765/api/today', method: 'GET'},
  respondWith(promise) { responsePromise = promise; },
});
await responsePromise;
assert.equal(fetchOptions.cache, 'no-store');
assert.equal(cacheTouched, false);

console.log('web runtime: navigation, rendering, units, and API cache bypass ok');
