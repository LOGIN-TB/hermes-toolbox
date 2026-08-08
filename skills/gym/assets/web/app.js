const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let displayUnits = 'metric';
let dashboardData = null;
let dashboardResult = null;
const dayNames = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];
const dayShort = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
const number = (value, digits = 1) => new Intl.NumberFormat('de-DE', {maximumFractionDigits: digits}).format(Number(value) || 0);
const weightValue = value => displayUnits === 'imperial' ? Number(value) / 0.45359237 : Number(value);
const weight = value => number(weightValue(value), 2);
const weightUnit = () => displayUnits === 'imperial' ? 'lb' : 'kg';
const volume = value => `${number(weightValue(value), 1)} ${weightUnit()}`;
const dateLabel = value => new Intl.DateTimeFormat('de-DE', {day: '2-digit', month: '2-digit', year: 'numeric'}).format(new Date(`${value}T12:00:00`));
const longDate = value => new Intl.DateTimeFormat('de-DE', {weekday: 'long', day: '2-digit', month: 'long'}).format(new Date(`${value}T12:00:00`));

async function api(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', credentials: 'same-origin', ...options});
  if (response.status === 401) {
    await clearDashboardSnapshot(dashboardStore);
    if (!$('login').open) $('login').showModal();
    throw new Error('login required');
  }
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

const OFFLINE_SNAPSHOT_VERSION = 1;
const OFFLINE_SNAPSHOT_MAX_BYTES = 2_000_000;

function createDashboardStore(driver) {
  const key = 'latest';
  return {
    read: () => driver.get(key),
    async write(snapshot) {
      const bytes = new TextEncoder().encode(JSON.stringify(snapshot)).byteLength;
      if (bytes > OFFLINE_SNAPSHOT_MAX_BYTES) throw new Error('Offline-Snapshot ist zu groß.');
      await driver.put(key, snapshot);
    },
    clear: () => driver.delete(key),
  };
}

function createIndexedDbDriver(factory) {
  let databasePromise;
  const openDatabase = () => {
    if (!factory) return Promise.reject(new Error('IndexedDB ist nicht verfügbar.'));
    if (!databasePromise) databasePromise = new Promise((resolve, reject) => {
      const request = factory.open('gympilot-dashboard', 1);
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains('snapshots')) database.createObjectStore('snapshots');
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('IndexedDB konnte nicht geöffnet werden.'));
      request.onblocked = () => reject(new Error('IndexedDB-Aktualisierung ist blockiert.'));
    });
    return databasePromise;
  };
  const transact = async (mode, operation) => {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction('snapshots', mode);
      const request = operation(transaction.objectStore('snapshots'));
      transaction.oncomplete = () => resolve(request.result ?? null);
      transaction.onerror = () => reject(transaction.error || request.error || new Error('IndexedDB-Transaktion fehlgeschlagen.'));
      transaction.onabort = () => reject(transaction.error || new Error('IndexedDB-Transaktion wurde abgebrochen.'));
    });
  };
  return {
    get: key => transact('readonly', store => store.get(key)),
    put: (key, value) => transact('readwrite', store => store.put(value, key)),
    delete: key => transact('readwrite', store => store.delete(key)),
  };
}

const dashboardStore = createDashboardStore(createIndexedDbDriver(globalThis.indexedDB));

async function clearDashboardSnapshot(store = dashboardStore) {
  try { await store.clear(); }
  catch (error) { console.warn('Offline-Snapshot konnte nicht gelöscht werden.', error); }
}

function validDashboardSnapshot(snapshot) {
  return Boolean(snapshot && snapshot.version === OFFLINE_SNAPSHOT_VERSION &&
    typeof snapshot.saved_at === 'string' && !Number.isNaN(Date.parse(snapshot.saved_at)) &&
    snapshot.health && snapshot.health.auth_required === false &&
    snapshot.today && Array.isArray(snapshot.today.plan) && snapshot.today.profile &&
    snapshot.overview && typeof snapshot.overview.date === 'string' &&
    snapshot.routines && typeof snapshot.routines === 'object' && !Array.isArray(snapshot.routines));
}

function isNetworkFailure(error) {
  return error instanceof TypeError && !Object.hasOwn(error, 'status');
}

async function resolveDashboardSnapshot(fetchLive, store, clock = () => new Date()) {
  try {
    const live = await fetchLive();
    const snapshot = {...live, version: OFFLINE_SNAPSHOT_VERSION, saved_at: clock().toISOString()};
    try {
      if (snapshot.health.auth_required) await store.clear();
      else await store.write(snapshot);
    } catch (cacheError) {
      console.warn('Offline-Snapshot konnte nicht gespeichert werden.', cacheError);
    }
    return {snapshot, offline: false};
  } catch (error) {
    if (!isNetworkFailure(error)) throw error;
    let cached;
    try { cached = await store.read(); }
    catch (cacheError) {
      console.warn('Offline-Snapshot konnte nicht gelesen werden.', cacheError);
      throw error;
    }
    if (!validDashboardSnapshot(cached)) throw error;
    return {snapshot: cached, offline: true};
  }
}

function dashboardStatusText(result) {
  if (!result.offline) return 'Aktuell';
  const stamp = new Date(result.snapshot.saved_at);
  const formatted = new Intl.DateTimeFormat('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(stamp);
  return `Offline · Stand ${formatted}`;
}

function updateDashboardStatus(result) {
  const offline = result.offline;
  $('dataStatus').textContent = dashboardStatusText(result);
  $('dataStatus').classList.toggle('offline', offline);
  $('healthDot').classList.toggle('offline', offline);
}

async function fetchLiveDashboard(client = api) {
  const health = await client('/api/health');
  const [today, overview] = await Promise.all([client('/api/today'), client('/api/overview')]);
  const details = await Promise.all(today.plan.map(routine => client(`/api/today?routine=${routine.id}`)));
  const routines = Object.fromEntries(today.plan.map((routine, index) => [String(routine.id), details[index]]));
  return {health, today, overview, routines};
}

function setRows(sets, emptyText) {
  if (!sets.length) return `<p class="empty">${esc(emptyText)}</p>`;
  return sets.map((set, index) => `<div class="set-line"><span>Satz ${esc(set.set_number || index + 1)}</span><strong>${weight(set.weight_kg)} ${weightUnit()}</strong><span>${esc(set.reps)} Wdh.</span>${set.equipment_alias ? `<small>${esc(set.equipment_alias)}</small>` : ''}</div>`).join('');
}

function exerciseCard(exercise, index, comparableDate) {
  const done = exercise.current_progress.completed_sets;
  const total = exercise.current_progress.planned_sets;
  return `<article class="exercise-card">
    <div class="exercise-head"><span class="exercise-number">${String(index + 1).padStart(2, '0')}</span><div><h2>${esc(exercise.name)}</h2><p>${total} Sätze · ${exercise.min_reps}–${exercise.max_reps} Wdh.</p></div><span class="badge">${done}/${total}</span></div>
    <div class="previous"><div class="subhead"><span>LETZTES TRAINING</span><small>${comparableDate ? dateLabel(comparableDate) : 'Kein Vergleich'}</small></div>${setRows(exercise.last_sets, 'Noch keine Vergleichssätze vorhanden.')}</div>
    ${exercise.current_sets.length ? `<div class="current"><div class="subhead"><span>HEUTE</span></div>${setRows(exercise.current_sets, 'Noch kein Satz protokolliert.')}</div>` : ''}
  </article>`;
}

function planCard(routine) {
  const targets = routine.exercises.map(exercise => `<li><span>${esc(exercise.name)}</span><strong>${exercise.planned_sets} × ${exercise.min_reps}–${exercise.max_reps}</strong></li>`).join('');
  return `<article class="plan-card"><div class="plan-head"><div><h2>${esc(routine.name)}</h2><p>${routine.weekdays.map(day => dayShort[day - 1]).join(' · ')}</p></div><span>${routine.exercises.length} Übungen</span></div><ul>${targets || '<li><span>Noch keine Übungen</span></li>'}</ul></article>`;
}

function volumeChart(series) {
  const width = 720, height = 280, left = 54, right = 18, top = 18, bottom = 46;
  const values = series.map(item => Number(item.volume) || 0);
  const maximum = Math.max(1, ...values);
  const usableWidth = width - left - right, usableHeight = height - top - bottom;
  const points = values.map((value, index) => {
    const x = left + (series.length < 2 ? usableWidth / 2 : index * usableWidth / (series.length - 1));
    const y = top + usableHeight - value / maximum * usableHeight;
    return [x, y];
  });
  const pointString = points.map(point => point.map(value => value.toFixed(1)).join(',')).join(' ');
  const area = points.length ? `${left},${top + usableHeight} ${pointString} ${left + usableWidth},${top + usableHeight}` : '';
  const grid = [0, .5, 1].map(ratio => {
    const y = top + usableHeight - ratio * usableHeight;
    return `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}"/><text x="${left - 10}" y="${y + 4}" text-anchor="end">${number(maximum * ratio, 0)}</text>`;
  }).join('');
  const labels = series.map((item, index) => index % 3 === 0 || index === series.length - 1 ? `<text x="${points[index][0]}" y="${height - 14}" text-anchor="middle">${new Intl.DateTimeFormat('de-DE', {day:'2-digit', month:'2-digit'}).format(new Date(`${item.week_start}T12:00:00`))}</text>` : '').join('');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Trainingsvolumen der letzten 12 Wochen"><g class="chart-grid">${grid}${labels}</g><polygon class="chart-area" points="${area}"/><polyline class="chart-line" points="${pointString}"/><g class="chart-points">${points.map(point => `<circle cx="${point[0]}" cy="${point[1]}" r="4"/>`).join('')}</g><text class="chart-peak" x="${width - right}" y="14" text-anchor="end">${number(maximum, 0)} ${weightUnit()}</text></svg>`;
}

function historyRows(items) {
  if (!items.length) return '<p class="empty">Noch keine abgeschlossenen Einheiten.</p>';
  return items.map(item => {
    const parsed = new Date(`${item.session_date}T12:00:00`);
    return `<div class="history-row"><time datetime="${esc(item.session_date)}"><strong>${parsed.getDate()}</strong><span>${new Intl.DateTimeFormat('de-DE', {month:'short'}).format(parsed).replace('.', '').toUpperCase()}</span></time><div><strong>${esc(item.routine_name)}</strong><span>${item.sets} Sätze · ${item.reps} Wdh.</span></div><div class="history-volume"><strong>${volume(item.volume)}</strong><span>Volumen</span></div></div>`;
  }).join('');
}

function selectView(name) {
  const valid = ['overview', 'training', 'progress', 'plan'];
  const selected = valid.includes(name) ? name : 'overview';
  document.querySelectorAll('[data-view]').forEach(view => { view.hidden = view.dataset.view !== selected; });
  document.querySelectorAll('nav [data-target]').forEach(link => link.classList.toggle('active', link.dataset.target === selected));
  globalThis.window?.scrollTo?.({top: 0, behavior: 'instant'});
}

function renderTraining(today) {
  const routine = today.routine;
  const weekday = routine?.weekdays?.[0] || today.weekday;
  $('trainingDay').textContent = dayNames[weekday - 1] || 'Training';
  $('trainingName').textContent = routine?.name || 'Heute ist kein Training eingeplant.';
  $('comparison').innerHTML = routine ? `<span class="eyebrow">VERGLEICHSBASIS</span><strong>${routine.last_comparable_session_date ? dateLabel(routine.last_comparable_session_date) : 'Noch keine Einheit'}</strong><small>${today.active_session ? 'Einheit aktiv' : 'Keine Einheit aktiv'}</small>` : '<span class="empty">Wähle einen Trainingstag aus deinem Plan.</span>';
  $('trainingExercises').innerHTML = routine?.exercises.length ? routine.exercises.map((exercise, index) => exerciseCard(exercise, index, routine.last_comparable_session_date)).join('') : '<article class="panel empty">Keine Übungen für diesen Tag.</article>';
  $('daySelector').querySelectorAll('button').forEach(button => button.classList.toggle('active', Number(button.dataset.routine) === routine?.id));
}

function renderDashboard(health, today, overview, routines = {}) {
  dashboardData = {health, today, overview, routines};
  displayUnits = today.profile.units === 'imperial' ? 'imperial' : 'metric';
  $('health').textContent = health.auth_required ? 'Lokal und geschützt' : 'Lokal und privat';
  $('logout').hidden = !health.auth_required;
  $('dashboardDate').textContent = longDate(overview.date).toUpperCase();
  const next = overview.next_routine;
  $('nextTraining').innerHTML = next ? `<span class="eyebrow">NÄCHSTER TRAININGSTAG</span><strong>${dayNames[next.weekday - 1]}</strong><p>${esc(next.name)}</p><small>${next.exercise_count} Übungen · ${next.planned_sets} Sätze</small>` : '<span class="eyebrow">TRAININGSPLAN</span><strong>Noch kein Trainingstag</strong><p>Importiere deinen Plan oder richte ihn manuell ein.</p>';
  const week = overview.this_week;
  $('weekSessions').textContent = week.sessions;
  $('weekSets').textContent = week.sets;
  $('weekReps').textContent = week.reps;
  $('weekVolume').textContent = volume(week.volume);
  const totals = overview.totals;
  $('totalSessions').textContent = totals.sessions;
  $('totalSets').textContent = totals.sets;
  $('totalReps').textContent = totals.reps;
  $('totalVolume').textContent = volume(totals.volume);
  const chart = volumeChart(overview.weekly_volume);
  $('overviewChart').innerHTML = chart;
  $('progressChart').innerHTML = chart;
  const history = historyRows(overview.recent_sessions);
  $('overviewHistory').innerHTML = history;
  $('progressHistory').innerHTML = history;
  $('allPlans').innerHTML = today.plan.length ? today.plan.map(planCard).join('') : '<article class="panel empty">Noch kein Trainingsplan.</article>';
  $('daySelector').innerHTML = today.plan.map(routine => `<button type="button" data-routine="${routine.id}"><strong>${routine.weekdays.map(day => dayShort[day - 1]).join('/')}</strong><span>${esc(routine.name)}</span></button>`).join('');
  $('daySelector').querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
    renderTraining(dashboardData.routines[String(button.dataset.routine)] || today);
  }));
  renderTraining(today);
}

async function loadDashboard() {
  const result = await resolveDashboardSnapshot(fetchLiveDashboard, dashboardStore);
  dashboardResult = result;
  const {health, today, overview, routines} = result.snapshot;
  renderDashboard(health, today, overview, routines);
  updateDashboardStatus(result);
}

function showUnavailable() {
  $('dataStatus').textContent = 'Offline · keine gespeicherten Daten';
  $('dataStatus').classList.add('offline');
  $('healthDot').classList.add('offline');
  $('nextTraining').innerHTML = '<span class="eyebrow">OFFLINE</span><strong>Keine gespeicherten Daten</strong><p>Verbinde dich einmal mit dem GymPilot-Server, um Auswertungen auf diesem Gerät zu speichern.</p>';
}

async function init() {
  window.addEventListener('hashchange', () => selectView(location.hash.slice(1)));
  document.querySelectorAll('nav [data-target]').forEach(link => link.addEventListener('click', () => selectView(link.dataset.target)));
  selectView(location.hash.slice(1));
  $('loginForm').addEventListener('submit', async event => {
    event.preventDefault();
    const response = await fetch('/api/login', {method: 'POST', cache: 'no-store', credentials: 'same-origin', headers: {'Content-Type':'application/json'}, body: JSON.stringify({password: $('password').value})});
    $('password').value = '';
    if (!response.ok) { $('loginError').textContent = response.status === 429 ? 'Zu viele Versuche. Bitte später erneut probieren.' : 'Ungültiges Passwort.'; return; }
    $('login').close(); $('loginError').textContent = ''; await loadDashboard();
  });
  $('logout').addEventListener('click', async () => {
    await clearDashboardSnapshot();
    await fetch('/api/logout', {method:'POST', cache:'no-store', credentials:'same-origin'});
    location.reload();
  });
  window.addEventListener('offline', () => {
    if (!dashboardResult) return;
    dashboardResult = {...dashboardResult, offline: true};
    updateDashboardStatus(dashboardResult);
  });
  $('dataStatus').addEventListener('click', () => loadDashboard().catch(error => console.error(error)));
  window.addEventListener('online', () => loadDashboard().catch(error => console.error(error)));
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) loadDashboard().catch(error => console.error(error));
  });
  try { await loadDashboard(); } catch (error) {
    console.error(error);
    if (error.message !== 'login required') showUnavailable();
  }
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js');
}

document.addEventListener('DOMContentLoaded', init);
