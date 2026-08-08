import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const viewNames = ['overview', 'training', 'progress', 'plan'];
const elements = {};
const views = viewNames.map(name => ({dataset: {view: name}, hidden: false}));
const links = viewNames.map(name => ({
  dataset: {target: name},
  classList: {active: false, toggle(_className, enabled) { this.active = enabled; }},
  addEventListener() {},
}));

globalThis.document = {
  documentElement: {lang: 'de'},
  addEventListener() {},
  getElementById(id) { return elements[id] ?? {}; },
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
  resolveDashboardSnapshot, dashboardStatusText, fetchLiveDashboard, createDashboardStore, createIndexedDbDriver,
  updateDashboardStatus, clearDashboardSnapshot, validDashboardSnapshot,
  setUnits: value => { displayUnits = value; }
};`);

const routineSummary = {
  id: 7, name: 'Beine', weekdays: [5],
  exercises: [{name: 'Beinpresse', planned_sets: 3, min_reps: 8, max_reps: 12}],
};
const routineDetail = {
  ...routineSummary,
  last_comparable_session_date: '2026-08-01',
  exercises: [{
    ...routineSummary.exercises[0],
    current_progress: {completed_sets: 0, planned_sets: 3},
    last_sets: [{set_number: 1, weight_kg: 80, reps: 10, equipment_alias: ''}],
    current_sets: [],
  }],
};
const todayData = {
  profile: {units: 'metric'}, plan: [routineSummary], routine: routineDetail,
  weekday: 6, active_session: null,
};
const liveData = {
  health: {status: 'ok', auth_required: false},
  today: todayData,
  overview: {
    date: '2026-08-08',
    this_week: {sessions: 1, sets: 3, reps: 30, volume: 2400},
    totals: {sessions: 8, sets: 24, reps: 240, volume: 19200},
    next_routine: {name: 'Beine', weekday: 5, exercise_count: 1, planned_sets: 3},
    weekly_volume: [{week_start: '2026-08-03', volume: 2400}],
    recent_sessions: [{session_date: '2026-08-01', routine_name: 'Beine', sets: 3, reps: 30, volume: 2400}],
  },
  routines: {'7': {...todayData, routine: routineDetail}},
};
let writtenSnapshot = null;
let clearCount = 0;
const onlineStore = {
  async read() { return null; },
  async write(value) { writtenSnapshot = value; },
  async clear() { clearCount += 1; },
};
const online = await __gymPilotTest.resolveDashboardSnapshot(
  async () => liveData, onlineStore, () => new Date('2026-08-08T16:30:00.000Z'),
);
assert.equal(online.offline, false);
assert.equal(online.snapshot.saved_at, '2026-08-08T16:30:00.000Z');
assert.deepEqual(writtenSnapshot.routines, liveData.routines);
assert.equal(clearCount, 0);

const malformedLive = structuredClone(liveData);
malformedLive.today.plan[0].id = '<img src=x onerror=alert(1)>';
await assert.rejects(
  __gymPilotTest.resolveDashboardSnapshot(
    async () => malformedLive, onlineStore, () => new Date('2026-08-08T16:30:00.000Z'),
  ),
  /Ungültige Dashboard-Daten/,
);

let cachedReads = 0;
const cachedSnapshot = {...writtenSnapshot, saved_at: '2026-08-08T15:15:00.000Z'};
const offlineStore = {
  async read() { cachedReads += 1; return cachedSnapshot; },
  async write() { throw new Error('must not write offline'); },
  async clear() {},
};
const offline = await __gymPilotTest.resolveDashboardSnapshot(
  async () => { throw new TypeError('Failed to fetch'); }, offlineStore,
);
assert.equal(offline.offline, true);
assert.equal(offline.snapshot, cachedSnapshot);
assert.equal(cachedReads, 1);
assert.match(__gymPilotTest.dashboardStatusText(offline), /Offline/);
assert.match(__gymPilotTest.dashboardStatusText(offline), /08\.08\.2026/);
function fakeClassList() {
  const values = new Set();
  return {toggle(name, enabled) { enabled ? values.add(name) : values.delete(name); }, contains: name => values.has(name)};
}
elements.dataStatus = {textContent: '', classList: fakeClassList()};
elements.healthDot = {classList: fakeClassList()};
__gymPilotTest.updateDashboardStatus(offline);
assert.match(elements.dataStatus.textContent, /Offline/);
assert.equal(elements.dataStatus.classList.contains('offline'), true);
assert.equal(elements.healthDot.classList.contains('offline'), true);

const httpError = new Error('HTTP 500');
httpError.status = 500;
cachedReads = 0;
await assert.rejects(
  __gymPilotTest.resolveDashboardSnapshot(async () => { throw httpError; }, offlineStore),
  /HTTP 500/,
);
assert.equal(cachedReads, 0);

writtenSnapshot = null;
clearCount = 0;
const protectedOnline = await __gymPilotTest.resolveDashboardSnapshot(
  async () => ({...liveData, health: {...liveData.health, auth_required: true}}),
  onlineStore,
  () => new Date('2026-08-08T16:30:00.000Z'),
);
assert.equal(protectedOnline.offline, false);
assert.equal(writtenSnapshot, null);
assert.equal(clearCount, 1);

let authClearCount = 0;
await __gymPilotTest.clearDashboardSnapshot({async clear() { authClearCount += 1; }});
assert.equal(authClearCount, 1);
await assert.rejects(
  __gymPilotTest.clearDashboardSnapshot({async clear() { throw new Error('delete failed'); }}),
  /delete failed/,
);

const originalWarn = console.warn;
console.warn = () => {};
const onlineWithoutCache = await __gymPilotTest.resolveDashboardSnapshot(
  async () => liveData,
  {async read() { return null; }, async write() { throw new Error('quota full'); }, async clear() {}},
  () => new Date('2026-08-08T16:30:00.000Z'),
);
console.warn = originalWarn;
assert.equal(onlineWithoutCache.offline, false);
assert.equal(onlineWithoutCache.snapshot.today, liveData.today);

await assert.rejects(
  __gymPilotTest.resolveDashboardSnapshot(
    async () => { throw new TypeError('Failed to fetch'); },
    {async read() { return {...cachedSnapshot, version: 999}; }, async write() {}, async clear() {}},
  ),
  /Failed to fetch/,
);

assert.equal(__gymPilotTest.validDashboardSnapshot(cachedSnapshot), true);
const corruptions = [
  snapshot => { delete snapshot.overview.this_week; },
  snapshot => { snapshot.overview.weekly_volume = null; },
  snapshot => { snapshot.overview.recent_sessions[0].session_date = 'not-a-date'; },
  snapshot => { snapshot.today.plan[0].weekdays = '5'; },
  snapshot => { snapshot.today.plan[0].id = '<img src=x onerror=alert(1)>'; },
  snapshot => { snapshot.routines['7'].routine.exercises[0].current_progress = null; },
  snapshot => { snapshot.routines['7'].routine.exercises[0].min_reps = '<svg onload=alert(1)>'; },
  snapshot => { snapshot.routines['7'].routine.id = 8; },
];
for (const corrupt of corruptions) {
  const corrupted = structuredClone(cachedSnapshot);
  corrupt(corrupted);
  assert.equal(__gymPilotTest.validDashboardSnapshot(corrupted), false);
  await assert.rejects(
    __gymPilotTest.resolveDashboardSnapshot(
      async () => { throw new TypeError('Failed to fetch'); },
      {async read() { return corrupted; }, async write() {}, async clear() {}},
    ),
    /Failed to fetch/,
  );
}

const requestedPaths = [];
const apiResponses = {
  '/api/health': {status: 'ok', auth_required: false},
  '/api/today': {profile: {units: 'metric'}, plan: [{id: 7}, {id: 8}], routine: {id: 7}},
  '/api/overview': {date: '2026-08-08'},
  '/api/today?routine=7': {routine: {id: 7, name: 'Beine'}},
  '/api/today?routine=8': {routine: {id: 8, name: 'Rücken'}},
};
const fetchedLive = await __gymPilotTest.fetchLiveDashboard(async path => {
  requestedPaths.push(path);
  return apiResponses[path];
});
assert.deepEqual(Object.keys(fetchedLive.routines), ['7', '8']);
assert.equal(fetchedLive.routines['8'].routine.name, 'Rücken');
assert.deepEqual(requestedPaths, [
  '/api/health', '/api/today', '/api/overview',
  '/api/today?routine=7', '/api/today?routine=8',
]);

let protectedSnapshot = cachedSnapshot;
let protectedClearCount = 0;
const protectedStore = {
  async read() { return protectedSnapshot; },
  async write() {},
  async clear() { protectedClearCount += 1; protectedSnapshot = null; },
};
await assert.rejects(
  __gymPilotTest.resolveDashboardSnapshot(
    () => __gymPilotTest.fetchLiveDashboard(async path => {
      if (path === '/api/health') return {status: 'ok', auth_required: true};
      throw new TypeError('later request failed');
    }, protectedStore),
    protectedStore,
  ),
  /later request failed/,
);
assert.equal(protectedClearCount, 1);
assert.equal(protectedSnapshot, null);

const records = new Map();
const dashboardStore = __gymPilotTest.createDashboardStore({
  async get(key) { return records.get(key) ?? null; },
  async put(key, value) { records.set(key, value); },
  async delete(key) { records.delete(key); },
});
await dashboardStore.write(cachedSnapshot);
assert.equal(await dashboardStore.read(), cachedSnapshot);
await dashboardStore.clear();
assert.equal(await dashboardStore.read(), null);
await assert.rejects(
  dashboardStore.write({...cachedSnapshot, oversized: 'x'.repeat(2_100_000)}),
  /zu groß/,
);

const policyState = new Map();
const deletionFailureStore = __gymPilotTest.createDashboardStore({
  async get() { return cachedSnapshot; },
  async put() {},
  async delete() { throw new Error('IndexedDB delete failed'); },
}, {
  getItem(key) { return policyState.get(key) ?? null; },
  setItem(key, value) { policyState.set(key, value); },
  removeItem(key) { policyState.delete(key); },
});
await assert.rejects(deletionFailureStore.clear(), /IndexedDB delete failed/);
assert.equal(await deletionFailureStore.read(), null);
const afterRestartStore = __gymPilotTest.createDashboardStore({
  async get() { return cachedSnapshot; },
  async put() {},
  async delete() {},
}, {
  getItem(key) { return policyState.get(key) ?? null; },
  setItem(key, value) { policyState.set(key, value); },
  removeItem(key) { policyState.delete(key); },
});
assert.equal(await afterRestartStore.read(), null);

let releaseStaleWrite;
let staleStored = cachedSnapshot;
const staleWriteStarted = new Promise(resolve => { releaseStaleWrite = resolve; });
let finishStaleWrite;
const racingPolicy = new Map();
const racingStore = __gymPilotTest.createDashboardStore({
  async get() { return staleStored; },
  async put(_key, value) {
    await new Promise(resolve => { finishStaleWrite = () => { staleStored = value; resolve(); }; });
  },
  async delete() { staleStored = null; },
}, {
  getItem(key) { return racingPolicy.get(key) ?? null; },
  setItem(key, value) { racingPolicy.set(key, value); releaseStaleWrite(); },
  removeItem(key) { racingPolicy.delete(key); },
});
const staleWrite = racingStore.write({...cachedSnapshot, saved_at: '2026-08-08T17:00:00.000Z'});
await new Promise(resolve => setImmediate(resolve));
const racingClear = racingStore.clear();
await staleWriteStarted;
finishStaleWrite();
await assert.rejects(staleWrite, /ungültig/i);
await racingClear;
assert.equal(await racingStore.read(), null);
assert.equal(racingPolicy.get('gympilot-dashboard-offline-blocked'), '1');

let releaseOldFetch;
const oldFetchGate = new Promise(resolve => { releaseOldFetch = resolve; });
let epochStored = cachedSnapshot;
const epochPolicy = new Map();
const epochStore = __gymPilotTest.createDashboardStore({
  async get() { return epochStored; },
  async put(_key, value) { epochStored = value; },
  async delete() { epochStored = null; },
}, {
  getItem(key) { return epochPolicy.get(key) ?? null; },
  setItem(key, value) { epochPolicy.set(key, value); },
  removeItem(key) { epochPolicy.delete(key); },
});
const oldFetch = __gymPilotTest.resolveDashboardSnapshot(async () => {
  await oldFetchGate;
  return liveData;
}, epochStore, () => new Date('2026-08-08T18:00:00.000Z'));
await new Promise(resolve => setImmediate(resolve));
await epochStore.clear();
releaseOldFetch();
await assert.rejects(oldFetch, /ungültig/i);
assert.equal(await epochStore.read(), null);
assert.equal(epochPolicy.get('gympilot-dashboard-offline-blocked'), '1');

const totalFailureStore = __gymPilotTest.createDashboardStore({
  async get() { return cachedSnapshot; },
  async put() {},
  async delete() { throw new Error('delete denied'); },
}, {
  getItem() { return null; },
  setItem() { throw new Error('marker denied'); },
  removeItem() {},
});
await assert.rejects(totalFailureStore.clear(), /Sperrmarke.*Löschen/);
assert.equal(await totalFailureStore.read(), null);

const idbRecords = new Map();
let openedDatabase = null;
let createdStore = null;
const fakeDb = {
  objectStoreNames: {contains: name => name === createdStore},
  createObjectStore(name) { createdStore = name; },
  transaction(_storeName, _mode) {
    const transaction = {error: null};
    transaction.objectStore = () => ({
      get(key) { return completeRequest(transaction, idbRecords.get(key) ?? null); },
      put(value, key) { idbRecords.set(key, value); return completeRequest(transaction, key); },
      delete(key) { idbRecords.delete(key); return completeRequest(transaction, undefined); },
    });
    return transaction;
  },
};
function completeRequest(transaction, result) {
  const request = {result, error: null};
  queueMicrotask(() => transaction.oncomplete?.());
  return request;
}
const fakeIndexedDb = {
  open(name, version) {
    openedDatabase = [name, version];
    const request = {result: fakeDb, error: null};
    queueMicrotask(() => { request.onupgradeneeded?.(); request.onsuccess?.(); });
    return request;
  },
};
const idbDriver = __gymPilotTest.createIndexedDbDriver(fakeIndexedDb);
await idbDriver.put('latest', cachedSnapshot);
assert.equal(await idbDriver.get('latest'), cachedSnapshot);
await idbDriver.delete('latest');
assert.equal(await idbDriver.get('latest'), null);
assert.deepEqual(openedDatabase, ['gympilot-dashboard', 1]);
assert.equal(createdStore, 'snapshots');

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
assert.match(index, /<title>GymPilot<\/title>/);
assert.match(index, /class="brand"[^>]*>.*<strong>GymPilot<\/strong>/);
assert.doesNotMatch(index, /Training Cockpit/);
assert.match(index, /<button[^>]+id="dataStatus"/);
assert.ok(styles.includes('.view[hidden]{display:none}'));
assert.match(appSource, /resolveDashboardSnapshot\(fetchLiveDashboard, dashboardStore\)/);
assert.match(appSource, /createDashboardStore\(createIndexedDbDriver\(globalThis\.indexedDB\)\)/);
for (const forbiddenPath of ['/api/session/start', '/api/set', '/api/session/finish', '/api/plan/']) {
  assert.equal(appSource.includes(forbiddenPath), false);
}
const mutationMethods = [...appSource.matchAll(/method\s*:\s*['"](POST|PUT|PATCH|DELETE)['"]/g)].map(match => match[1]);
assert.deepEqual(mutationMethods, ['POST', 'POST']);
assert.match(appSource, /fetch\('\/api\/login'/);
assert.match(appSource, /fetch\('\/api\/logout'/);
assert.match(appSource, /\$\('dataStatus'\)\.addEventListener\('click'/);
assert.match(appSource, /document\.addEventListener\('visibilitychange'/);

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
assert.match(fs.readFileSync('skills/gym/assets/web/service-worker.js', 'utf8'), /gympilot-shell-v11/);
assert.match(fs.readFileSync('skills/gym/assets/web/service-worker.js', 'utf8'), /cache:\s*['"]reload['"]/);
assert.equal(typeof fetchHandler, 'function');
let responsePromise;
fetchHandler({
  request: {url: 'http://127.0.0.1:8765/api/today', method: 'GET'},
  respondWith(promise) { responsePromise = promise; },
});
await responsePromise;
assert.equal(fetchOptions.cache, 'no-store');
assert.equal(cacheTouched, false);

let coldFetchHandler;
let activateHandler;
let releaseClaim;
const claimPromise = new Promise(resolve => { releaseClaim = resolve; });
const shellResponse = {ok: true, source: 'cached-index'};
const coldContext = vm.createContext({
  URL,
  Request: class { constructor(path, options) { this.url = path; this.cache = options?.cache; } },
  location: {origin: 'http://127.0.0.1:8765'},
  fetch: async () => { throw new TypeError('server offline'); },
  caches: {
    async match(request) { return request === '/index.html' ? shellResponse : null; },
    async open() { return {put: async () => {}}; },
    async keys() { return ['gympilot-shell-v8', 'gympilot-shell-v9']; },
    async delete() { return true; },
  },
  self: {
    clients: {claim: () => claimPromise},
    skipWaiting() {},
    addEventListener(name, handler) {
      if (name === 'fetch') coldFetchHandler = handler;
      if (name === 'activate') activateHandler = handler;
    },
  },
});
vm.runInContext(fs.readFileSync('skills/gym/assets/web/service-worker.js', 'utf8'), coldContext);

let coldResponsePromise;
coldFetchHandler({
  request: {url: 'http://127.0.0.1:8765/app-launch?source=homescreen', method: 'GET', mode: 'navigate'},
  respondWith(promise) { coldResponsePromise = promise; },
});
assert.equal(await coldResponsePromise, shellResponse);

let activationPromise;
activateHandler({waitUntil(promise) { activationPromise = promise; }});
let activationFinished = false;
activationPromise.then(() => { activationFinished = true; });
await new Promise(resolve => setImmediate(resolve));
assert.equal(activationFinished, false);
releaseClaim();
await activationPromise;
assert.equal(activationFinished, true);

console.log('web runtime: cockpit navigation, comparison cards, charts, history, units, and API cache bypass ok');
