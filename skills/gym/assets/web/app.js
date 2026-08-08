const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let displayUnits = 'metric';
const weight = value => new Intl.NumberFormat(displayUnits === 'imperial' ? 'en-US' : 'de-DE', {maximumFractionDigits: 2}).format(displayUnits === 'imperial' ? Number(value) / 0.45359237 : Number(value));
const weightUnit = () => displayUnits === 'imperial' ? 'lb' : 'kg';
const days = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];

async function api(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', credentials: 'same-origin', ...options});
  if (response.status === 401) {
    if (!$('login').open) $('login').showModal();
    throw new Error('login required');
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function setRows(sets, emptyText) {
  if (!sets.length) return `<span class="empty">${esc(emptyText)}</span>`;
  return sets.map(set => `<span class="set-pill">${set.equipment_alias ? `${esc(set.equipment_alias)} · ` : ''}${set.side ? `${esc(set.side)} · ` : ''}${weight(set.weight_kg)} ${weightUnit()} × ${set.reps}</span>`).join('');
}

function exerciseCard(exercise, index, comparableDate) {
  const done = exercise.current_progress.completed_sets;
  const total = exercise.current_progress.planned_sets;
  return `<article class="exercise-card">
    <div class="exercise-head"><div><small>ÜBUNG ${index + 1}</small><h3>${esc(exercise.name)}</h3><p class="target">Ziel: ${total} Sätze · ${exercise.min_reps}–${exercise.max_reps} Wdh.</p></div><span class="badge">${done}/${total}</span></div>
    <div class="set-group"><strong>Letztes Mal${comparableDate ? ` · ${esc(comparableDate)}` : ''}</strong><div class="set-row">${setRows(exercise.last_sets, 'Kein Vergleichssatz')}</div></div>
    <div class="set-group current"><strong>Heute</strong><div class="set-row">${setRows(exercise.current_sets, 'Noch kein Satz')}</div></div>
  </article>`;
}

function planCard(routine) {
  const targets = routine.exercises.map(exercise => `<li>${esc(exercise.name)} <span>${exercise.planned_sets} × ${exercise.min_reps}–${exercise.max_reps}</span></li>`).join('');
  return `<article class="plan-card"><h3>${esc(routine.name)}</h3><p>${routine.weekdays.map(day => days[day - 1]).join(' · ')}</p><ul>${targets || '<li>Noch keine Übungen</li>'}</ul></article>`;
}

function selectView(name) {
  const valid = ['today', 'plan', 'progress', 'settings'];
  const selected = valid.includes(name) ? name : 'today';
  document.querySelectorAll('[data-view]').forEach(view => { view.hidden = view.dataset.view !== selected; });
  document.querySelectorAll('nav [data-target]').forEach(link => link.classList.toggle('active', link.dataset.target === selected));
}

async function loadDashboard() {
  const [health, today, overview] = await Promise.all([api('/api/health'), api('/api/today'), api('/api/overview')]);
  $('health').textContent = health.auth_required ? 'LOKAL · GESCHÜTZT' : 'LOKAL · PRIVAT';
  $('logout').hidden = !health.auth_required;
  $('sessions').textContent = overview.sessions;
  $('sets').textContent = overview.sets;
  displayUnits = today.profile.units === 'imperial' ? 'imperial' : 'metric';
  $('volume').textContent = `${weight(overview.volume)} ${weightUnit()}`;
  $('profile').textContent = `${today.profile.display_name || 'GymPilot'} · ${today.profile.units === 'imperial' ? 'Imperial' : 'Metrisch'} · ${today.profile.goal || 'Ziel nicht angegeben'}`;
  const routine = today.routine;
  $('title').innerHTML = routine ? `${esc(routine.name)},<br><em>du bist bereit.</em>` : 'Erholungstag,<br><em>bleib in Bewegung.</em>';
  $('subtitle').textContent = routine ? 'Ziele, letzter Vergleich und heutige Sätze auf einen Blick.' : 'Diesem Wochentag ist kein Training zugeordnet.';
  $('todayPlan').innerHTML = routine?.exercises.length ? routine.exercises.map((exercise, index) => exerciseCard(exercise, index, routine.last_comparable_session_date)).join('') : '<article class="last">Heute sind keine Übungen geplant.</article>';
  const planned = routine?.exercises.reduce((sum, exercise) => sum + exercise.planned_sets, 0) || 0;
  const completed = routine?.exercises.reduce((sum, exercise) => sum + exercise.current_sets.length, 0) || 0;
  $('progress').textContent = planned ? `${Math.min(100, Math.round(completed / planned * 100))}%` : '0%';
  $('last').textContent = routine?.last_comparable_session_date ? `${routine.last_comparable_session_date} · ${routine.name}` : 'Noch kein vergleichbares Training für diesen Plan.';
  $('allPlans').innerHTML = today.plan.length ? today.plan.map(planCard).join('') : '<article class="last">Noch kein Trainingsplan.</article>';
  document.documentElement.lang = 'de';
}

async function init() {
  window.addEventListener('hashchange', () => selectView(location.hash.slice(1)));
  document.querySelectorAll('nav [data-target]').forEach(link => link.addEventListener('click', () => selectView(link.dataset.target)));
  selectView(location.hash.slice(1));
  $('loginForm').addEventListener('submit', async event => {
    event.preventDefault();
    const response = await fetch('/api/login', {method: 'POST', cache: 'no-store', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({password: $('password').value})});
    $('password').value = '';
    if (!response.ok) { $('loginError').textContent = response.status === 429 ? 'Zu viele Versuche. Bitte später erneut probieren.' : 'Ungültiges Passwort.'; return; }
    $('login').close(); $('loginError').textContent = ''; await loadDashboard();
  });
  $('logout').addEventListener('click', async () => { await fetch('/api/logout', {method: 'POST', cache: 'no-store', credentials: 'same-origin'}); location.reload(); });
  try { await loadDashboard(); } catch (error) { console.error(error); }
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js');
}

document.addEventListener('DOMContentLoaded', init);
