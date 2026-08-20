const $ = id => document.getElementById(id);
const GYMPILOT_WEB_BUILD = 'balanced-progress-v24';
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let displayUnits = 'metric';
let dashboardData = null;
let dashboardResult = null;
let lastDashboardError = null;
let lastOfflineStoreError = null;
const dayNames = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];
const dayShort = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
const THEME_KEY = 'gympilot-theme';
const nextTheme = theme => theme === 'light' ? 'dark' : 'light';
function applyTheme(theme) {
  const selected = theme === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = selected;
  const meta = document.querySelector?.('meta[name="theme-color"]');
  if (meta) meta.content = selected === 'light' ? '#f5f6fa' : '#08090d';
  const toggle = $('themeToggle');
  if (toggle?.setAttribute) {
    const light = selected === 'light';
    toggle.setAttribute('aria-checked', String(!light));
    toggle.setAttribute('aria-label', 'Dunkelmodus');
    toggle.title = light ? 'Dunkle Darstellung' : 'Helle Darstellung';
  }
  return selected;
}
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

const OFFLINE_SNAPSHOT_VERSION = 3;
const OFFLINE_SNAPSHOT_MAX_BYTES = 2_000_000;

function availablePolicyStorage() {
  try { return globalThis.localStorage ?? null; }
  catch (_error) { return null; }
}

function createCacheStorageDriver(cacheStorage) {
  const cacheName = 'gympilot-private-dashboard-v3';
  const requestKey = key => `/__gympilot_private_dashboard_snapshot__/${encodeURIComponent(key)}`;
  return {
    async get(key) {
      const cache = await cacheStorage.open(cacheName);
      const response = await cache.match(requestKey(key));
      return response ? response.json() : null;
    },
    async put(key, value) {
      const cache = await cacheStorage.open(cacheName);
      await cache.put(requestKey(key), new Response(JSON.stringify(value), {
        headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'},
      }));
    },
    async delete(key) {
      const cache = await cacheStorage.open(cacheName);
      await cache.delete(requestKey(key));
    },
  };
}

function createMirroredDashboardDriver(drivers) {
  return {
    async get(key) {
      const outcomes = await Promise.allSettled(drivers.map(driver => driver.get(key)));
      const candidates = outcomes
        .filter(outcome => outcome.status === 'fulfilled' && validDashboardSnapshot(outcome.value, true))
        .map(outcome => outcome.value);
      if (candidates.length) return candidates.reduce((newest, candidate) => (
        !newest || Date.parse(candidate.saved_at) > Date.parse(newest.saved_at) ? candidate : newest
      ), null);
      const errors = outcomes.filter(outcome => outcome.status === 'rejected').map(outcome => outcome.reason);
      if (errors.length === outcomes.length) throw new AggregateError(errors, 'Kein Offline-Speicher konnte gelesen werden.');
      return null;
    },
    async put(key, value) {
      const outcomes = await Promise.allSettled(drivers.map(driver => driver.put(key, value)));
      if (outcomes.some(outcome => outcome.status === 'fulfilled')) return;
      throw new AggregateError(outcomes.map(outcome => outcome.reason), 'Kein Offline-Speicher konnte beschrieben werden.');
    },
    async delete(key) {
      const outcomes = await Promise.allSettled(drivers.map(driver => driver.delete(key)));
      const errors = outcomes.filter(outcome => outcome.status === 'rejected').map(outcome => outcome.reason);
      if (errors.length) throw new AggregateError(errors, 'Nicht alle Offline-Speicher konnten gelöscht werden.');
    },
  };
}

function createDashboardStore(driver, policyStorage = availablePolicyStorage()) {
  const blockedKey = 'gympilot-dashboard-offline-blocked';
  const allowedKey = 'gympilot-dashboard-offline-allowed';
  const epochLabel = epoch => epoch === null ? 'initial' : String(epoch);
  const storageKey = epoch => `latest:${epochLabel(epoch)}`;
  const fallbackKey = epoch => `gympilot-dashboard-offline-snapshot:${epochLabel(epoch)}`;
  let blocked = false;
  let generation = 0;
  let mutationTail = Promise.resolve();
  const enqueueMutation = operation => {
    const result = mutationTail.then(operation, operation);
    mutationTail = result.catch(() => {});
    return result;
  };
  const isBlocked = () => {
    if (blocked) return true;
    if (!policyStorage) return true;
    try { return policyStorage.getItem(blockedKey) !== policyStorage.getItem(allowedKey); }
    catch (_error) { return true; }
  };
  const policyEpoch = () => {
    if (!policyStorage) return undefined;
    try { return policyStorage.getItem(blockedKey) ?? null; }
    catch (_error) { return undefined; }
  };
  return {
    generation: () => generation,
    policyEpoch,
    async diagnostics() {
      const report = {policy_storage: Boolean(policyStorage), blocked: true};
      if (!policyStorage) return report;
      try {
        const blockEpoch = policyStorage.getItem(blockedKey);
        const allowEpoch = policyStorage.getItem(allowedKey);
        report.block_epoch = blockEpoch;
        report.allow_epoch = allowEpoch;
        report.blocked = blockEpoch !== allowEpoch;
        const epoch = blockEpoch ?? null;
        const key = storageKey(epoch);
        const localFallbackKey = fallbackKey(epoch);
        report.storage_key = key;
        try {
          const primary = await driver.get(key);
          report.primary = {
            present: Boolean(primary), valid: validDashboardSnapshot(primary, true),
            saved_at: primary?.saved_at ?? null, plans: primary?.today?.plan?.length ?? null,
          };
        } catch (error) { report.primary = {error: `${error?.name || 'Error'}: ${error?.message || error}`}; }
        try {
          const raw = policyStorage.getItem(localFallbackKey);
          const fallback = raw ? JSON.parse(raw) : null;
          report.local_fallback = {
            present: Boolean(raw), bytes: raw?.length ?? 0, valid: validDashboardSnapshot(fallback, true),
            saved_at: fallback?.saved_at ?? null, plans: fallback?.today?.plan?.length ?? null,
          };
        } catch (error) { report.local_fallback = {error: `${error?.name || 'Error'}: ${error?.message || error}`}; }
      } catch (error) { report.policy_error = `${error?.name || 'Error'}: ${error?.message || error}`; }
      return report;
    },
    allowWrites(expectedEpoch) {
      return enqueueMutation(async () => {
        if (!policyStorage || expectedEpoch === undefined) throw new Error('Persistenter Richtlinienspeicher ist nicht verfügbar.');
        const currentEpoch = policyStorage.getItem(blockedKey);
        if (currentEpoch !== expectedEpoch) throw new Error('Dashboard-Abruf wurde durch eine neuere Sperre ungültig.');
        if (currentEpoch === null) policyStorage.removeItem(allowedKey);
        else policyStorage.setItem(allowedKey, currentEpoch);
        if (policyStorage.getItem(blockedKey) !== policyStorage.getItem(allowedKey)) {
          blocked = true;
          throw new Error('Dashboard-Abruf wurde durch eine neuere Sperre ungültig.');
        }
        blocked = false;
        generation += 1;
        return {generation, policyEpoch: currentEpoch};
      });
    },
    async read() {
      const startedAt = generation;
      if (isBlocked()) return null;
      const startedEpoch = policyEpoch();
      if (startedEpoch === undefined) return null;
      const key = storageKey(startedEpoch);
      const localFallbackKey = fallbackKey(startedEpoch);
      let primarySnapshot = null;
      let fallbackSnapshot = null;
      let primaryError = null;
      let fallbackError = null;
      try { primarySnapshot = await driver.get(key); }
      catch (error) { primaryError = error; }
      try {
        const raw = policyStorage.getItem(localFallbackKey);
        if (raw) fallbackSnapshot = JSON.parse(raw);
      } catch (error) { fallbackError = error; }
      const candidates = [primarySnapshot, fallbackSnapshot].filter(candidate => validDashboardSnapshot(candidate, true));
      const snapshot = candidates.reduce((newest, candidate) => (
        !newest || Date.parse(candidate.saved_at) > Date.parse(newest.saved_at) ? candidate : newest
      ), null);
      if (!snapshot) {
        if (primaryError && fallbackError) throw new AggregateError([primaryError, fallbackError], 'Offline-Snapshot konnte nicht gelesen werden.');
        if (primaryError) throw primaryError;
        if (fallbackError) throw fallbackError;
      }
      return startedAt === generation && policyEpoch() === startedEpoch && !isBlocked() ? snapshot : null;
    },
    write(snapshot, expectedAuthorization = {generation, policyEpoch: policyEpoch()}) {
      const serialized = JSON.stringify(snapshot);
      const bytes = new TextEncoder().encode(serialized).byteLength;
      if (bytes > OFFLINE_SNAPSHOT_MAX_BYTES) return Promise.reject(new Error('Offline-Snapshot ist zu groß.'));
      const startedAt = typeof expectedAuthorization === 'object' ? expectedAuthorization.generation : expectedAuthorization;
      const authorizedEpoch = typeof expectedAuthorization === 'object' ? expectedAuthorization.policyEpoch : policyEpoch();
      const key = storageKey(authorizedEpoch);
      const localFallbackKey = fallbackKey(authorizedEpoch);
      return enqueueMutation(async () => {
        if (authorizedEpoch === undefined || startedAt !== generation || policyEpoch() !== authorizedEpoch || isBlocked()) {
          throw new Error('Offline-Snapshot wurde durch eine neuere Sperre ungültig.');
        }
        let primaryError = null;
        let fallbackError = null;
        try { await driver.put(key, snapshot); }
        catch (error) { primaryError = error; }
        try {
          if (policyStorage) policyStorage.setItem(localFallbackKey, serialized);
          else fallbackError = new Error('Lokaler Fallback-Speicher ist nicht verfügbar.');
        } catch (error) { fallbackError = error; }
        if (primaryError && fallbackError) {
          throw new AggregateError([primaryError, fallbackError], 'Offline-Snapshot konnte nicht gespeichert werden.');
        }
        if (startedAt !== generation || policyEpoch() !== authorizedEpoch || isBlocked()) {
          try { await driver.delete(key); }
          catch (cleanupError) {
            throw new AggregateError([cleanupError], 'Ungültiger Offline-Snapshot konnte nicht entfernt werden.');
          }
          try { policyStorage?.removeItem(localFallbackKey); }
          catch (_error) {}
          throw new Error('Offline-Snapshot wurde durch eine neuere Sperre ungültig.');
        }
        blocked = false;
      });
    },
    clear() {
      const clearedEpoch = policyEpoch();
      const key = storageKey(clearedEpoch ?? null);
      const localFallbackKey = fallbackKey(clearedEpoch ?? null);
      generation += 1;
      blocked = true;
      let markerError = null;
      try {
        if (policyStorage) policyStorage.setItem(blockedKey, `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`);
        else markerError = new Error('Persistenter Richtlinienspeicher ist nicht verfügbar.');
      } catch (error) { markerError = error; }
      return enqueueMutation(async () => {
        let fallbackDeleteError = null;
        if (!policyStorage) fallbackDeleteError = new Error('Lokaler Fallback-Speicher ist nicht verfügbar.');
        else {
          try { policyStorage.removeItem(localFallbackKey); }
          catch (error) { fallbackDeleteError = error; }
        }
        try { await driver.delete(key); }
        catch (deleteError) {
          if (markerError || fallbackDeleteError) {
            throw new AggregateError(
              [markerError, fallbackDeleteError, deleteError].filter(Boolean),
              'Sperrmarke konnte nicht gespeichert und Snapshot nicht durch Löschen invalidiert werden.',
            );
          }
          throw deleteError;
        }
        if (fallbackDeleteError) {
          if (markerError) {
            throw new AggregateError([markerError, fallbackDeleteError], 'Sperrmarke und lokaler Fallback konnten nicht gelöscht werden.');
          }
          throw fallbackDeleteError;
        }
      });
    },
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

const dashboardDrivers = [createIndexedDbDriver(globalThis.indexedDB)];
if (globalThis.caches) dashboardDrivers.push(createCacheStorageDriver(globalThis.caches));
const dashboardStore = createDashboardStore(createMirroredDashboardDriver(dashboardDrivers));

async function clearDashboardSnapshot(store = dashboardStore) {
  await store.clear();
}

const isRecord = value => Boolean(value && typeof value === 'object' && !Array.isArray(value));
const isSafeInteger = value => Number.isSafeInteger(value) && value >= 0;
const isNumber = value => typeof value === 'number' && Number.isFinite(value);
const isFiniteNumber = value => isNumber(value) && value >= 0;
const isNullableNumber = value => value === null || isNumber(value);
const isWeekday = value => Number.isInteger(value) && value >= 1 && value <= 7;
const isIsoDate = value => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
};
const isOptionalIsoDate = value => value === null || isIsoDate(value);
const isMetricBlock = value => isRecord(value) && ['sessions', 'sets', 'reps'].every(key => isSafeInteger(value[key])) && isFiniteNumber(value.volume);
const isPlanExercise = exercise => isRecord(exercise) && typeof exercise.name === 'string' &&
  isSafeInteger(exercise.planned_sets) && isSafeInteger(exercise.min_reps) && isSafeInteger(exercise.max_reps);
const isWorkoutSet = set => isRecord(set) && isSafeInteger(set.set_number) &&
  isFiniteNumber(set.weight_kg) && isSafeInteger(set.reps) &&
  (set.equipment_alias === null || typeof set.equipment_alias === 'string');
const isRoutineSummary = routine => isRecord(routine) && Number.isSafeInteger(routine.id) && routine.id > 0 &&
  typeof routine.name === 'string' && Array.isArray(routine.weekdays) && routine.weekdays.every(isWeekday) &&
  Array.isArray(routine.exercises) && routine.exercises.every(isPlanExercise);
const isRoutineDetail = routine => isRoutineSummary(routine) && isOptionalIsoDate(routine.last_comparable_session_date) &&
  routine.exercises.every(exercise => isRecord(exercise.current_progress) &&
    isSafeInteger(exercise.current_progress.completed_sets) && isSafeInteger(exercise.current_progress.planned_sets) &&
    Array.isArray(exercise.last_sets) && exercise.last_sets.every(isWorkoutSet) &&
    Array.isArray(exercise.current_sets) && exercise.current_sets.every(isWorkoutSet));
const isTodayPayload = today => isRecord(today) && isRecord(today.profile) &&
  ['metric', 'imperial'].includes(today.profile.units) && isWeekday(today.weekday) &&
  Array.isArray(today.plan) && today.plan.every(isRoutineSummary) &&
  (today.routine === null || isRoutineDetail(today.routine));
const isProgressPoint = point => isRecord(point) &&
  Number.isSafeInteger(point.session_id) && point.session_id > 0 && isIsoDate(point.session_date) &&
  isSafeInteger(point.sets) && isSafeInteger(point.reps) && isFiniteNumber(point.volume) &&
  (point.best_weight_kg === null || isFiniteNumber(point.best_weight_kg)) &&
  (point.best_reps === null || isSafeInteger(point.best_reps)) &&
  isFiniteNumber(point.estimated_1rm_kg) &&
  (point.average_weight_kg === null || isFiniteNumber(point.average_weight_kg)) &&
  isSafeInteger(point.target_sets) && typeof point.ready_to_increase === 'boolean' &&
  Array.isArray(point.equipment_key) && point.equipment_key.every(isSafeInteger) &&
  (point.equipment_alias === null || typeof point.equipment_alias === 'string');
const isLatestComparison = comparison => comparison === null || (isRecord(comparison) &&
  Number.isSafeInteger(comparison.routine_id) && comparison.routine_id > 0 &&
  typeof comparison.routine_name === 'string' && isIsoDate(comparison.session_date) &&
  isOptionalIsoDate(comparison.previous_date) && isSafeInteger(comparison.sets) &&
  isSafeInteger(comparison.reps) && isFiniteNumber(comparison.volume) &&
  (comparison.duration_minutes === null || isSafeInteger(comparison.duration_minutes)) &&
  isNullableNumber(comparison.volume_pct) && isNullableNumber(comparison.reps_delta));
const isHighlight = highlight => isRecord(highlight) &&
  Number.isSafeInteger(highlight.exercise_id) && highlight.exercise_id > 0 &&
  typeof highlight.exercise_name === 'string' && ['weight', 'reps', 'volume'].includes(highlight.kind) &&
  isNumber(highlight.value) && isProgressPoint(highlight.latest);
const isOverviewPayload = overview => isRecord(overview) && isIsoDate(overview.date) &&
  isMetricBlock(overview.this_week) && isMetricBlock(overview.totals) &&
  isRecord(overview.week_adherence) && isSafeInteger(overview.week_adherence.completed) &&
  isSafeInteger(overview.week_adherence.planned) &&
  Array.isArray(overview.week_schedule) && overview.week_schedule.every(item =>
    isRecord(item) && typeof item.name === 'string' && typeof item.day_name === 'string' &&
    isWeekday(item.weekday) && isIsoDate(item.scheduled_date) &&
    ['completed', 'today', 'missed', 'upcoming'].includes(item.status)) &&
  (overview.next_routine === null || (isRecord(overview.next_routine) && typeof overview.next_routine.name === 'string' &&
    isWeekday(overview.next_routine.weekday) && isSafeInteger(overview.next_routine.exercise_count) &&
    isSafeInteger(overview.next_routine.planned_sets) && isSafeInteger(overview.next_routine.days_until))) &&
  Array.isArray(overview.recent_sessions) && overview.recent_sessions.every(item =>
    isRecord(item) && isIsoDate(item.session_date) && typeof item.routine_name === 'string' &&
    isSafeInteger(item.sets) && isSafeInteger(item.reps) && isFiniteNumber(item.volume)) &&
  isLatestComparison(overview.latest_comparison) &&
  Array.isArray(overview.highlights) && overview.highlights.every(isHighlight);
const isProgressSession = session => isRecord(session) &&
  Number.isSafeInteger(session.id) && session.id > 0 &&
  Number.isSafeInteger(session.routine_id) && session.routine_id > 0 &&
  isIsoDate(session.session_date) && isSafeInteger(session.sets) &&
  isSafeInteger(session.reps) && isFiniteNumber(session.volume) &&
  (session.duration_minutes === null || isSafeInteger(session.duration_minutes));
const isProgressExercise = exercise => isRecord(exercise) && Number.isSafeInteger(exercise.exercise_id) &&
  exercise.exercise_id > 0 && typeof exercise.name === 'string' &&
  isSafeInteger(exercise.planned_sets) && isSafeInteger(exercise.min_reps) &&
  isSafeInteger(exercise.max_reps) && isSafeInteger(exercise.sessions_count) &&
  isRecord(exercise.change) &&
  ['new', 'improved', 'stable', 'mixed', 'declined'].includes(exercise.change.status) &&
  isNullableNumber(exercise.change.volume_pct) && isNullableNumber(exercise.change.reps_delta) &&
  isNullableNumber(exercise.change.best_weight_delta_kg) &&
  isNullableNumber(exercise.change.estimated_1rm_pct) &&
  isNullableNumber(exercise.change.average_weight_pct) &&
  isNullableNumber(exercise.change.target_sets_delta) &&
  Array.isArray(exercise.history) && exercise.history.every(isProgressPoint) &&
  (exercise.latest === null || isProgressPoint(exercise.latest)) &&
  (exercise.previous === null || isProgressPoint(exercise.previous)) &&
  (exercise.record === null || isProgressPoint(exercise.record));
const isProgressPayload = progress => isRecord(progress) && isIsoDate(progress.date) &&
  Array.isArray(progress.routines) && progress.routines.every(routine =>
    isRecord(routine) && Number.isSafeInteger(routine.id) && routine.id > 0 &&
    typeof routine.name === 'string' && isSafeInteger(routine.sessions_count) &&
    isRecord(routine.change) && isNullableNumber(routine.change.volume_pct) &&
    isNullableNumber(routine.change.reps_delta) && isSafeInteger(routine.improved_exercises) &&
    (routine.latest === null || isProgressSession(routine.latest)) &&
    (routine.previous === null || isProgressSession(routine.previous)) &&
    Array.isArray(routine.exercises) && routine.exercises.every(isProgressExercise) &&
    Array.isArray(routine.history) && routine.history.every(isProgressSession)) &&
  Array.isArray(progress.recent_sessions) && progress.recent_sessions.every(isProgressSession);

function validDashboardSnapshot(snapshot, allowProtected = false) {
  if (!isRecord(snapshot) || snapshot.version !== OFFLINE_SNAPSHOT_VERSION ||
      typeof snapshot.saved_at !== 'string' || Number.isNaN(Date.parse(snapshot.saved_at)) ||
      !isRecord(snapshot.health) || typeof snapshot.health.auth_required !== 'boolean' ||
      (!allowProtected && snapshot.health.auth_required) ||
      !isTodayPayload(snapshot.today) || !isOverviewPayload(snapshot.overview) ||
      !isProgressPayload(snapshot.progress) || !isRecord(snapshot.routines)) return false;
  try {
    if (new TextEncoder().encode(JSON.stringify(snapshot)).byteLength > OFFLINE_SNAPSHOT_MAX_BYTES) return false;
  } catch (_error) { return false; }
  const plannedIds = new Set(snapshot.today.plan.map(routine => String(routine.id)));
  const routineKeys = Object.keys(snapshot.routines);
  if (routineKeys.length !== plannedIds.size || routineKeys.some(key => !plannedIds.has(key))) return false;
  return routineKeys.every(key => {
    const payload = snapshot.routines[key];
    return isTodayPayload(payload) && payload.routine !== null && String(payload.routine.id) === key;
  });
}

function isNetworkFailure(error) {
  return (error instanceof TypeError && !Object.hasOwn(error, 'status')) || error?.name === 'AbortError';
}

async function resolveDashboardSnapshot(fetchLive, store, clock = () => new Date()) {
  const startedAt = store.generation?.();
  const startedPolicyEpoch = store.policyEpoch?.();
  try {
    const live = await fetchLive();
    if (startedAt !== undefined && startedAt !== store.generation() && !live.health?.auth_required) {
      throw new Error('Dashboard-Abruf wurde durch eine neuere Sperre ungültig.');
    }
    const snapshot = {...live, version: OFFLINE_SNAPSHOT_VERSION, saved_at: clock().toISOString()};
    if (!validDashboardSnapshot(snapshot, true)) throw new Error('Ungültige Dashboard-Daten.');
    try {
      if (snapshot.health.auth_required) await store.clear();
      else {
        const writeGeneration = store.allowWrites ? await store.allowWrites(startedPolicyEpoch) : startedAt;
        await store.write(snapshot, writeGeneration);
        lastOfflineStoreError = null;
      }
    } catch (cacheError) {
      lastOfflineStoreError = `${cacheError?.name || 'Error'}: ${cacheError?.message || cacheError}`;
      if (cacheError?.message?.includes('neuere Sperre')) throw cacheError;
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

function fetchDashboardWithTimeout(fetchLive, timeoutMs = 6000) {
  const controller = new AbortController();
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      const error = new Error('Dashboard-Abruf hat das Zeitlimit überschritten.');
      error.name = 'AbortError';
      controller.abort();
      reject(error);
    }, timeoutMs);
    Promise.resolve()
      .then(() => fetchLive(controller.signal))
      .then(resolve, reject)
      .finally(() => clearTimeout(timeout));
  });
}

async function fetchLiveDashboard(client = api, store = dashboardStore, signal = undefined) {
  const health = await client('/api/health', {signal});
  if (health.auth_required) await store.clear();
  const [today, overview, progress] = await Promise.all([
    client('/api/today', {signal}), client('/api/overview', {signal}), client('/api/progress', {signal}),
  ]);
  const details = await Promise.all(today.plan.map(routine => client(`/api/today?routine=${routine.id}`, {signal})));
  const routines = Object.fromEntries(today.plan.map((routine, index) => [String(routine.id), details[index]]));
  return {health, today, overview, progress, routines};
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
    return `<div class="history-row"><time datetime="${esc(item.session_date)}"><strong>${parsed.getDate()}</strong><span>${new Intl.DateTimeFormat('de-DE', {month:'short'}).format(parsed).replace('.', '').toUpperCase()}</span></time><div><strong>${esc(item.routine_name)}</strong><span>${item.sets} Sätze · ${item.reps} Wdh.${item.duration_minutes ? ` · ${item.duration_minutes} Min.` : ''}</span></div><div class="history-volume"><strong>${volume(item.volume)}</strong><span>Volumen</span></div></div>`;
  }).join('');
}

const signed = (value, suffix = '', digits = 1) => {
  if (value === null || value === undefined) return '–';
  const numeric = Number(value);
  return `${numeric > 0 ? '+' : ''}${number(numeric, digits)}${suffix}`;
};

function weekScheduleRows(items) {
  if (!items.length) return '<p class="empty">Noch keine Trainingstage geplant.</p>';
  const icons = {completed: '✓', today: '●', missed: '!', upcoming: '○'};
  const labels = {completed: 'Erledigt', today: 'Heute', missed: 'Offen', upcoming: 'Geplant'};
  return items.map(item => `<div class="week-day ${item.status}"><span class="week-state" aria-hidden="true">${icons[item.status]}</span><div><strong>${esc(item.day_name.slice(0, 2))}</strong><small>${esc(item.name)}</small></div><em>${labels[item.status]}</em></div>`).join('');
}

function highlightRows(items) {
  if (!items.length) return '<p class="empty">Nach zwei vergleichbaren Einheiten erscheinen hier konkrete Verbesserungen.</p>';
  return items.map(item => {
    let detail = `${signed(item.value, ' %')} mehr Volumen`;
    if (item.kind === 'weight') detail = `${signed(weightValue(item.value), ` ${weightUnit()}`, 2)} beim besten Arbeitssatz`;
    if (item.kind === 'reps') detail = `${signed(item.value)} Wiederholungen`;
    const best = item.latest?.best_weight_kg === null || item.latest?.best_weight_kg === undefined ? '' :
      `<small>Aktuell ${weight(item.latest.best_weight_kg)} ${weightUnit()} × ${item.latest.best_reps}</small>`;
    return `<div class="highlight-row"><span aria-hidden="true">↗</span><div><strong>${esc(item.exercise_name)}</strong><p>${esc(detail)}</p>${best}</div></div>`;
  }).join('');
}

function latestComparisonCard(comparison) {
  if (!comparison) return '<p class="empty">Noch keine abgeschlossene Einheit.</p>';
  const change = comparison.volume_pct === null ? 'Noch keine Vergleichseinheit' :
    `${signed(comparison.volume_pct, ' %')} Volumen zur gleichen Routine`;
  return `<div class="panel-head"><div><span class="eyebrow">LETZTE EINHEIT</span><h2>${esc(comparison.routine_name)}</h2></div><time datetime="${esc(comparison.session_date)}">${dateLabel(comparison.session_date)}</time></div>
    <div class="comparison-facts"><div><strong>${comparison.sets}</strong><span>Sätze</span></div><div><strong>${comparison.reps}</strong><span>Wdh.</span></div><div><strong>${volume(comparison.volume)}</strong><span>Volumen</span></div>${comparison.duration_minutes ? `<div><strong>${comparison.duration_minutes}</strong><span>Minuten</span></div>` : ''}</div>
    <p class="comparison-change ${comparison.volume_pct > 0 ? 'positive' : ''}">${esc(change)}</p>`;
}

function exerciseTrend(history) {
  const points = history.filter(item => item.best_weight_kg !== null);
  if (points.length < 3) return '';
  const width = 360, height = 94, left = 14, right = 14, top = 12, bottom = 24;
  const values = points.map(item => weightValue(item.best_weight_kg));
  const minimum = Math.min(...values), maximum = Math.max(...values);
  const range = Math.max(maximum - minimum, 1);
  const coordinates = values.map((value, index) => [
    left + index * (width - left - right) / Math.max(points.length - 1, 1),
    top + (maximum - value) / range * (height - top - bottom),
  ]);
  const line = coordinates.map(point => point.map(value => value.toFixed(1)).join(',')).join(' ');
  return `<div class="exercise-trend"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Bestes Arbeitsgewicht im Verlauf"><polyline points="${line}"/>${coordinates.map((point, index) => `<circle cx="${point[0]}" cy="${point[1]}" r="3"/><text x="${point[0]}" y="${height - 7}" text-anchor="middle">${new Intl.DateTimeFormat('de-DE', {day:'2-digit', month:'2-digit'}).format(new Date(`${points[index].session_date}T12:00:00`))}</text>`).join('')}</svg></div>`;
}

function exerciseProgressCard(exercise) {
  const latest = exercise.latest;
  if (!latest) return `<article class="panel progress-exercise"><div class="progress-exercise-head"><div><span class="eyebrow">${exercise.min_reps}–${exercise.max_reps} WDH.</span><h2>${esc(exercise.name)}</h2></div><span class="progress-badge new">Keine Daten</span></div></article>`;
  const previous = exercise.previous;
  const change = exercise.change;
  const statusLabels = {improved: 'Verbessert', stable: 'Stabil', mixed: 'Gemischt', declined: 'Rückgang', new: 'Ausgangswert'};
  const best = latest.best_weight_kg === null ? 'Kein Arbeitssatz' : `${weight(latest.best_weight_kg)} ${weightUnit()} × ${latest.best_reps}`;
  const previousBest = !previous ? 'Kein Vergleich' : previous.best_weight_kg === null ? 'Kein Arbeitssatz' : `${weight(previous.best_weight_kg)} ${weightUnit()} × ${previous.best_reps}`;
  const record = exercise.record?.best_weight_kg === null || !exercise.record ? '–' : `${weight(exercise.record.best_weight_kg)} ${weightUnit()} × ${exercise.record.best_reps}`;
  const deltaParts = [];
  if (change.best_weight_delta_kg !== null) deltaParts.push(`Top-Satz ${signed(weightValue(change.best_weight_delta_kg), ` ${weightUnit()}`, 2)}`);
  if (change.estimated_1rm_pct !== null) deltaParts.push(`Leistungswert ${signed(change.estimated_1rm_pct, ' %')}`);
  if (change.volume_pct !== null) deltaParts.push(`Volumen ${signed(change.volume_pct, ' %')}`);
  if (change.target_sets_delta !== null && change.target_sets_delta !== 0) deltaParts.push(`Zielsätze ${signed(change.target_sets_delta)}`);
  const comparison = previous ? deltaParts.join(' · ') : 'Erster Ausgangswert';
  return `<article class="panel progress-exercise">
    <div class="progress-exercise-head"><div><span class="eyebrow">${exercise.min_reps}–${exercise.max_reps} WDH. · ${exercise.planned_sets} SÄTZE</span><h2>${esc(exercise.name)}</h2>${latest.equipment_alias ? `<small>${esc(latest.equipment_alias)}</small>` : ''}</div><span class="progress-badge ${change.status}">${statusLabels[change.status]}</span></div>
    <div class="progress-comparison"><div><span>Vorher</span><strong>${esc(previousBest)}</strong><small>${previous ? dateLabel(previous.session_date) : 'Noch kein Vergleich'}</small></div><span class="comparison-arrow" aria-hidden="true">→</span><div><span>Aktuell</span><strong>${esc(best)}</strong><small>${dateLabel(latest.session_date)}</small></div></div>
    <div class="exercise-stats"><span><strong>${latest.target_sets}/${exercise.planned_sets}</strong> Sätze im Ziel</span><span><strong>${weight(latest.average_weight_kg)} ${weightUnit()}</strong> Ø Arbeitsgewicht</span><span><strong>${weight(latest.estimated_1rm_kg)} ${weightUnit()}</strong> Leistungswert</span><span><strong>${volume(latest.volume)}</strong> Volumen</span><span><strong>${esc(record)}</strong> Bestleistung</span></div>
    <p class="exercise-change ${change.status}">${esc(comparison)}${latest.ready_to_increase ? ' · Oberes Wiederholungsziel erreicht' : ''}</p>
    ${exerciseTrend(exercise.history)}
  </article>`;
}

function renderProgress(progress, routineId = null) {
  const routines = progress.routines;
  if (!routines.length) {
    $('progressRoutineSelector').innerHTML = '';
    $('progressRoutineSummary').innerHTML = '<p class="empty">Noch kein Trainingsplan vorhanden.</p>';
    $('exerciseProgressList').innerHTML = '';
    $('progressHistory').innerHTML = '<p class="empty">Noch keine abgeschlossenen Einheiten.</p>';
    return;
  }
  const selected = routines.find(item => item.id === Number(routineId)) ||
    routines.find(item => item.sessions_count > 0) || routines[0];
  $('progressRoutineSelector').innerHTML = routines.map(routine => `<button type="button" data-progress-routine="${routine.id}" class="${routine.id === selected.id ? 'active' : ''}"><strong>${routine.sessions_count}</strong><span>${esc(routine.name)}</span></button>`).join('');
  $('progressRoutineSelector').querySelectorAll('button').forEach(button => button.addEventListener('click', () => renderProgress(progress, Number(button.dataset.progressRoutine))));
  const latest = selected.latest;
  if (!latest) {
    $('progressRoutineSummary').innerHTML = `<span class="eyebrow">${esc(selected.name)}</span><h2>Noch keine Einheit</h2><p class="empty">Nach dem ersten Training erscheint hier dein Ausgangswert.</p>`;
  } else {
    const volumeChange = selected.change.volume_pct === null ? 'Kein Vergleich' : signed(selected.change.volume_pct, ' %');
    const repsChange = selected.change.reps_delta === null ? '–' : signed(selected.change.reps_delta);
    $('progressRoutineSummary').innerHTML = `<div class="panel-head"><div><span class="eyebrow">ROUTINENVERGLEICH</span><h2>${esc(selected.name)}</h2></div><time datetime="${esc(latest.session_date)}">${dateLabel(latest.session_date)}</time></div><div class="comparison-facts"><div><strong>${volume(latest.volume)}</strong><span>letztes Volumen</span></div><div><strong>${esc(volumeChange)}</strong><span>zur vorherigen Einheit</span></div><div><strong>${esc(repsChange)}</strong><span>Wdh. verändert</span></div><div><strong>${selected.improved_exercises}</strong><span>Übungen verbessert</span></div></div>`;
  }
  $('exerciseProgressList').innerHTML = selected.exercises.map(exerciseProgressCard).join('');
  $('progressHistoryTitle').textContent = selected.name;
  $('progressHistory').innerHTML = historyRows(selected.history.map(item => ({...item, routine_name: selected.name})));
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

function renderDashboard(health, today, overview, progress, routines = {}) {
  dashboardData = {health, today, overview, progress, routines};
  displayUnits = today.profile.units === 'imperial' ? 'imperial' : 'metric';
  $('health').textContent = health.auth_required ? 'Lokal und geschützt' : 'Lokal und privat';
  $('logout').hidden = !health.auth_required;
  $('dashboardDate').textContent = longDate(overview.date).toUpperCase();
  const next = overview.next_routine;
  if (next) {
    const when = next.days_until === 0 ? 'Heute' : next.days_until === 1 ? 'Morgen' : dayNames[next.weekday - 1];
    $('nextTraining').innerHTML = `<span class="eyebrow">NÄCHSTER TRAININGSTAG</span><strong>${when}</strong><p>${esc(next.name)}</p><small>${next.exercise_count} Übungen · ${next.planned_sets} Sätze</small>`;
  } else {
    $('nextTraining').innerHTML = '<span class="eyebrow">TRAININGSPLAN</span><strong>Noch kein Trainingstag</strong><p>Importiere deinen Plan oder richte ihn manuell ein.</p>';
  }
  const adherence = overview.week_adherence;
  $('weekGoal').textContent = `${adherence.completed} von ${adherence.planned} Einheiten absolviert`;
  $('weekSchedule').innerHTML = weekScheduleRows(overview.week_schedule);
  const week = overview.this_week;
  $('weekSessions').textContent = week.sessions;
  $('weekSets').textContent = week.sets;
  $('weekReps').textContent = week.reps;
  $('latestComparison').innerHTML = latestComparisonCard(overview.latest_comparison);
  $('overviewHighlights').innerHTML = highlightRows(overview.highlights);
  $('overviewHistory').innerHTML = historyRows(overview.recent_sessions.slice(0, 3));
  $('allPlans').innerHTML = today.plan.length ? today.plan.map(planCard).join('') : '<article class="panel empty">Noch kein Trainingsplan.</article>';
  $('daySelector').innerHTML = today.plan.map(routine => `<button type="button" data-routine="${routine.id}"><strong>${routine.weekdays.map(day => dayShort[day - 1]).join('/')}</strong><span>${esc(routine.name)}</span></button>`).join('');
  $('daySelector').querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
    renderTraining(dashboardData.routines[String(button.dataset.routine)] || today);
  }));
  renderTraining(today);
  renderProgress(progress);
}

async function loadDashboard() {
  try {
    const result = await resolveDashboardSnapshot(
      () => fetchDashboardWithTimeout(signal => fetchLiveDashboard(api, dashboardStore, signal)),
      dashboardStore,
    );
    dashboardResult = result;
    const {health, today, overview, progress, routines} = result.snapshot;
    renderDashboard(health, today, overview, progress, routines);
    updateDashboardStatus(result);
    lastDashboardError = null;
    return result;
  } catch (error) {
    lastDashboardError = `${error?.name || 'Error'}: ${error?.message || error}`;
    throw error;
  }
}

async function collectGymPilotDiagnostics() {
  const report = {
    build: GYMPILOT_WEB_BUILD,
    generated_at: new Date().toISOString(),
    href: location.href,
    origin: location.origin,
    secure_context: globalThis.isSecureContext,
    online: navigator.onLine,
    standalone_media: globalThis.matchMedia?.('(display-mode: standalone)')?.matches ?? null,
    navigator_standalone: navigator.standalone ?? null,
    user_agent: navigator.userAgent,
    last_dashboard_error: lastDashboardError,
    last_offline_store_error: lastOfflineStoreError,
    dashboard_result: dashboardResult ? {offline: dashboardResult.offline, saved_at: dashboardResult.snapshot?.saved_at ?? null, plans: dashboardResult.snapshot?.today?.plan?.length ?? null} : null,
    store: await dashboardStore.diagnostics(),
  };
  try {
    const registration = await navigator.serviceWorker?.getRegistration();
    report.service_worker = {
      controller: navigator.serviceWorker?.controller?.scriptURL ?? null,
      active: registration?.active?.scriptURL ?? null,
      active_state: registration?.active?.state ?? null,
      waiting: registration?.waiting?.scriptURL ?? null,
      installing: registration?.installing?.scriptURL ?? null,
    };
  } catch (error) { report.service_worker = {error: `${error?.name || 'Error'}: ${error?.message || error}`}; }
  try {
    report.cache_names = await globalThis.caches?.keys() ?? null;
    if (globalThis.caches) {
      const privateCache = await globalThis.caches.open('gympilot-private-dashboard-v3');
      const requests = await privateCache.keys();
      report.private_cache = [];
      for (const request of requests) {
        const response = await privateCache.match(request);
        let snapshot = null;
        try { snapshot = response ? await response.clone().json() : null; } catch (_error) {}
        report.private_cache.push({
          path: new URL(request.url).pathname,
          present: Boolean(response), valid: validDashboardSnapshot(snapshot, true),
          saved_at: snapshot?.saved_at ?? null, plans: snapshot?.today?.plan?.length ?? null,
        });
      }
    }
  } catch (error) { report.cache_error = `${error?.name || 'Error'}: ${error?.message || error}`; }
  return report;
}

async function showDiagnostics() {
  const dialog = $('diagnostics');
  $('diagnosticsOutput').textContent = 'Diagnose wird geladen …';
  dialog.showModal();
  try { $('diagnosticsOutput').textContent = JSON.stringify(await collectGymPilotDiagnostics(), null, 2); }
  catch (error) { $('diagnosticsOutput').textContent = `${error?.name || 'Error'}: ${error?.message || error}`; }
}

function showUnavailable() {
  $('dataStatus').textContent = 'Offline · keine gespeicherten Daten';
  $('dataStatus').classList.add('offline');
  $('healthDot').classList.add('offline');
  $('nextTraining').innerHTML = '<span class="eyebrow">OFFLINE</span><strong>Keine gespeicherten Daten</strong><p>Verbinde dich einmal mit dem GymPilot-Server, um Auswertungen auf diesem Gerät zu speichern.</p>';
}

async function init() {
  applyTheme(document.documentElement.dataset.theme);
  $('themeToggle').addEventListener('click', () => {
    const selected = applyTheme(nextTheme(document.documentElement.dataset.theme));
    try { localStorage.setItem(THEME_KEY, selected); } catch (_error) {}
  });
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
  $('dataStatus').addEventListener('click', () => showDiagnostics());
  $('refreshDashboard').addEventListener('click', event => { event.preventDefault(); loadDashboard().then(showDiagnostics).catch(showDiagnostics); });
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
