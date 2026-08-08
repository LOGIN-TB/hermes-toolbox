import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const viewNames = ['overview', 'training', 'progress', 'plan'];
const views = viewNames.map(name => ({dataset: {view: name}, hidden: false}));
const links = viewNames.map(name => ({
  dataset: {target: name},
  classList: {active: false, toggle(_className, enabled) { this.active = enabled; }},
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
vm.runInThisContext(`${appSource}\nglobalThis.__gymPilotTest = {
  selectView, exerciseCard, volumeChart, historyRows,
  setUnits: value => { displayUnits = value; }
};`);

__gymPilotTest.selectView('training');
assert.equal(views.find(view => view.dataset.view === 'training').hidden, false);
assert.equal(views.find(view => view.dataset.view === 'overview').hidden, true);
assert.equal(links.find(link => link.dataset.target === 'training').classList.active, true);
assert.equal(links.find(link => link.dataset.target === 'overview').classList.active, false);

const exercise = {
  name: 'Beinpresse', planned_sets: 3, min_reps: 8, max_reps: 12,
  current_progress: {completed_sets: 1, planned_sets: 3},
  last_sets: [{weight_kg: 87.5, reps: 10, side: '', equipment_alias: 'Beinpresse Studio A', set_number: 1}],
  current_sets: [{weight_kg: 90, reps: 9, side: '', equipment_alias: 'Beinpresse Studio A', set_number: 1}],
};
__gymPilotTest.setUnits('metric');
const metricCard = __gymPilotTest.exerciseCard(exercise, 0, '2026-08-01');
assert.match(metricCard, /Beinpresse Studio A/);
assert.match(metricCard, /87,5 kg/);
assert.match(metricCard, /10 Wdh\./);
assert.match(metricCard, /1\/3/);

__gymPilotTest.setUnits('imperial');
const imperialCard = __gymPilotTest.exerciseCard({...exercise, last_sets: [{weight_kg: 45.359237, reps: 8, side: '', equipment_alias: '', set_number: 1}]}, 0, '2026-08-01');
assert.match(imperialCard, /100 lb/);
assert.match(imperialCard, /8 Wdh\./);

const chart = __gymPilotTest.volumeChart([
  {week_start: '2026-07-20', volume: 0},
  {week_start: '2026-07-27', volume: 1200},
  {week_start: '2026-08-03', volume: 2400},
]);
assert.match(chart, /<svg/);
assert.match(chart, /aria-label="Trainingsvolumen der letzten 12 Wochen"/);
assert.match(chart, /<polyline/);
assert.match(chart, /2\.400/);

__gymPilotTest.setUnits('metric');
const history = __gymPilotTest.historyRows([
  {session_date: '2026-08-07', routine_name: 'Beine', sets: 17, reps: 176, volume: 14767.5},
]);
assert.match(history, /Beine/);
assert.match(history, /17 Sätze · 176 Wdh\./);
assert.match(history, /14\.767,5 kg/);

const index = fs.readFileSync('skills/gym/assets/web/index.html', 'utf8');
const styles = fs.readFileSync('skills/gym/assets/web/styles.css', 'utf8');
for (const name of viewNames) {
  assert.match(index, new RegExp(`data-view="${name}"`));
  assert.match(index, new RegExp(`data-target="${name}"`));
}
for (const label of ['Übersicht', 'Training', 'Fortschritt', 'Plan']) assert.match(index, new RegExp(label));
assert.ok(styles.includes('.view[hidden]{display:none}'));

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

console.log('web runtime: cockpit navigation, comparison cards, charts, history, units, and API cache bypass ok');
