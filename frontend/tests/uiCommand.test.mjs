// Unit tests for the strict ui.command validator + alias resolution.
// Run:  node frontend/tests/uiCommand.test.mjs   (exit code 0 = all pass)
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  validateUiCommand, resolvePageName, parseNavigationRequest,
  unknownPageMessage, allowedFilters, setNavigationData, UI_COMMAND_ACTIONS,
} from '../src/components/voice/uiCommand.js';
import { NAV_ITEMS } from '../src/config/nav.js';

// Inject the SAME shared JSON the app loads (config/navigationData.js).
const shared = JSON.parse(readFileSync(new URL('../../shared/navigation.json', import.meta.url), 'utf8'));
setNavigationData(shared);

let passed = 0;
const ok = (label) => { passed += 1; console.log(`PASS ${label}`); };

// ---------------------------------------------------------------- navigate
for (const item of NAV_ITEMS) {
  const v = validateUiCommand({ action: 'navigate', page: item.id });
  assert.equal(v.ok, true, `navigate must accept nav id '${item.id}': ${v.error}`);
  assert.equal(v.args.page, item.id);
}
ok(`navigate accepts all ${NAV_ITEMS.length} nav ids`);

// Every id in shared/navigation.json must exist in nav.js (no drift).
for (const id of Object.keys(shared.pages)) {
  assert.ok(NAV_ITEMS.some((n) => n.id === id), `shared JSON page '${id}' missing from nav.js`);
}
ok('shared JSON page ids all exist in nav.js');

// ------------------------------------------------------- unknown pages
for (const bad of ['banana', 'nope', 'https://evil.com', 'http://x', 'javascript:alert(1)',
  'file:///etc/passwd', '<script>alert(1)</script>', 'dashboard; drop table']) {
  const v = validateUiCommand({ action: 'navigate', page: bad });
  assert.equal(v.ok, false, `must reject page '${bad}'`);
  if (bad === 'banana' || bad === 'nope') {
    assert.match(v.error, /I don't have a page called/, 'unknown page needs the spoken answer');
    const list = v.error.split('I can open: ')[1]?.split(', ') || [];
    assert.ok(list.length <= 6 && list.length >= 1, `suggestions must be <=6, got ${list.length}`);
  }
}
ok('rejects unknown pages, external URLs and script-like strings (with <=6 suggestions)');

// ------------------------------------------------- extra / malformed fields
const extraCases = [
  { action: 'navigate', page: 'machines', url: 'https://evil.com' },
  { action: 'navigate', page: 'machines', script: 'alert(1)' },
  { action: 'navigate', page: 'machines', machine: 'M-001' },
  { action: 'show_proposals', page: 'machines' },
  { action: 'select_machine', machine: 'M-001', filter: 'OPEN' },
  { action: 'open_order', order: 'ORD-001', incident: 'x' },
  { action: 'navigate', action2: 'navigate' },
];
for (const c of extraCases) {
  const v = validateUiCommand(c);
  assert.equal(v.ok, false, `must reject extra fields: ${JSON.stringify(c)}`);
  assert.match(v.error, /unexpected field/);
}
const malformed = [
  { action: 'navigate' },                       // missing page
  { action: 'navigate', page: '' },             // empty page
  { action: 'navigate', page: '   ' },          // blank page
  { action: 'navigate', page: 42 },             // wrong type
  { action: 'navigate', page: ['machines'] },   // wrong type
  { action: 'navigate', page: { id: 'machines' } },
  { action: 'navigate', page: 'x'.repeat(200) }, // too long
  { action: 'select_machine' },
  { action: 'open_order' },
  { action: 'open_incident' },
  { action: 'focus_order_on_map' },
  { action: 'delete_everything' },              // unknown action
  { action: null },
  'not json at all {',
  [1, 2, 3],
  null,
];
for (const c of malformed) {
  const v = validateUiCommand(c);
  assert.equal(v.ok, false, `must reject malformed: ${JSON.stringify(c)}`);
}
ok('rejects extra and malformed fields for every action');

// ------------------------------------------------------------- filters
const v1 = validateUiCommand({ action: 'navigate', page: 'incidents', filter: 'OPEN' });
assert.equal(v1.ok, true, v1.error);
assert.equal(v1.args.filter, 'OPEN');
const v2 = validateUiCommand({ action: 'navigate', page: 'machines', filter: 'OPEN' });
assert.equal(v2.ok, false, 'machines has no OPEN filter');
const v3 = validateUiCommand({ action: 'navigate', page: 'incidents', filter: 'open' });
assert.equal(v3.ok, false, 'filter must be the canonical value, not natural words');
const v4 = validateUiCommand({ action: 'navigate', page: 'iot', filter: 'OPEN' });
assert.equal(v4.ok, false, 'iot has no voice filters');
const v5 = validateUiCommand({ action: 'navigate', page: 'plans', filter: 'progress' });
assert.equal(v5.ok, true, v5.error);
const v6 = validateUiCommand({ action: 'navigate', page: 'tasks', filter: '<script>' });
assert.equal(v6.ok, false, 'unsafe filter rejected');
assert.deepEqual(allowedFilters('incidents'), ['OPEN', 'IN_PROGRESS', 'RESOLVED']);
assert.deepEqual(allowedFilters('iot'), []);
ok('filter validation: allowed canonical values only, per-page lists');

// ------------------------------------------------------- alias table (60+)
const ALIASES = [
  // phrase, expected page, expected filter (null = none)
  ['navigate to the Machines tab', 'machines', null],
  ['the machines tab please', 'machines', null],
  ['machine page', 'machines', null],
  ['machines', 'machines', null],
  ['equipment', 'machines', null],
  ['go to production', 'production', null],
  ['go to production page', 'production', null],
  ['production runs', 'production', null],
  ['open the factory map', 'map', null],
  ['floor map', 'map', null],
  ['factory floor', 'map', null],
  ['shop floor', 'map', null],
  ['take me to employees', 'employees', null],
  ['take me to the employees please', 'employees', null],
  ['staff', 'employees', null],
  ['workers', 'employees', null],
  ['people', 'employees', null],
  ['employee list', 'employees', null],
  ['workforce', 'employees', null],
  ['jobs', 'tasks', null],
  ['to-do', 'tasks', null],
  ['to do', 'tasks', null],
  ['tasks tab', 'tasks', null],
  ['assignments', 'tasks', null],
  ['show work plans progress tracker', 'plans', 'progress'],
  ['open the progress tracker', 'plans', 'progress'],
  ['work plan', 'plans', null],
  ['live plan', 'plans', 'live'],
  ['plans', 'plans', null],
  ['customer orders', 'orders', null],
  ['open orders', 'orders', null],
  ['sales orders', 'orders', null],
  ['sensors', 'iot', null],
  ['iot', 'iot', null],
  ['monitoring', 'iot', null],
  ['telemetry', 'iot', null],
  ['sensor data', 'iot', null],
  ['alerts', 'incidents', null],
  ['issues', 'incidents', null],
  ['problems', 'incidents', null],
  ['incident list', 'incidents', null],
  ['show open incidents', 'incidents', 'OPEN'],
  ['unresolved incidents', 'incidents', 'OPEN'],
  ['memory', 'memory', null],
  ['history', 'memory', null],
  ['decisions', 'memory', null],
  ['event log', 'memory', null],
  ['scenarios', 'simulate', null],
  ['simulate', 'simulate', null],
  ['what if', 'simulate', null],
  ['what-if', 'simulate', null],
  ['assistant', 'ai', null],
  ['chat', 'ai', null],
  ['ai assistant', 'ai', null],
  ['settings', 'profile', null],
  ['factory setup', 'profile', null],
  ['factory profile', 'profile', null],
  ['upload', 'import', null],
  ['import data', 'import', null],
  ['excel', 'import', null],
  ['dashboard', 'dashboard', null],
  ['home', 'dashboard', null],
  ['overview', 'dashboard', null],
  ['command center', 'dashboard', null],
  ['reports', 'reports', null],
  ['weekly report', 'reports', null],
  ['users', 'users', null],
  ['accounts', 'users', null],
  ['jarvis', 'jarvis', null],
  ['voice', 'jarvis', null],
  ['simulator', 'simulator', null],
  ['demo', 'simulator', null],
  // noisy variants
  ['please open the machines tab', 'machines', null],
  ['can you open reports for me', 'reports', null],
  ['show me the factory map', 'map', null],
  ['switch to the ai assistant', 'ai', null],
  ['jump to tasks', 'tasks', null],
  ['pull up incidents', 'incidents', null],
  ['head to orders', 'orders', null],
  ['ok now open the staff page', 'employees', null],
];
assert.ok(ALIASES.length >= 40, 'alias table must cover at least 40 phrases');
for (const [phrase, page, filter] of ALIASES) {
  const got = resolvePageName(phrase);
  assert.ok(got, `alias '${phrase}' did not resolve`);
  assert.equal(got.page, page, `alias '${phrase}' -> ${got.page}, expected ${page}`);
  assert.equal(got.filter || null, filter, `alias '${phrase}' filter ${got.filter}, expected ${filter}`);
}
ok(`alias resolution: ${ALIASES.length} phrases resolve to the right page/filter`);

// ------------------------------------------- typed gate (text assistant)
const navYes = ['open machines', 'go to production', 'navigate to reports',
  'take me to employees', 'show me the tasks tab', 'machines', 'what if', 'open the progress tracker'];
for (const t of navYes) {
  assert.ok(parseNavigationRequest(t), `typed '${t}' should navigate`);
}
const navNo = ["what's happening in production?", 'which incidents are open?',
  'show me the status of M-001', 'assign welding to Ravi', 'why is my order late?',
  'which machines need attention?', ''];
for (const t of navNo) {
  assert.equal(parseNavigationRequest(t), null, `typed '${t}' must go to the AI, not navigate`);
}
ok('parseNavigationRequest: nav verbs navigate, questions go to the AI');

// ------------------------------------------- unknown page spoken message
const msg = unknownPageMessage('banana page');
assert.match(msg, /^I don't have a page called banana page; I can open: /);
const labels = msg.split('I can open: ')[1].split(', ');
assert.ok(labels.length <= 6, `expected <=6 suggestions, got ${labels.length}`);
ok('unknownPageMessage: spoken answer with at most six page names');

assert.equal(UI_COMMAND_ACTIONS.length, 6, 'six whitelisted actions only');
ok('action whitelist unchanged (6 actions)');

// ------------------------------------------------- fuzzy near-miss (STT typos)
const FUZZY = [
  ['order tab', 'orders'],
  ['orders tub', 'orders'],
  ['ordas tab', 'orders'],
  ['machine tab', 'machines'],
  ['production tab', 'production'],
  ['employee tab', 'employees'],
  ['employees tap', 'employees'],
  ['go to the orders tab', 'orders'],
];
for (const [phrase, page] of FUZZY) {
  const got = resolvePageName(phrase);
  assert.ok(got, `fuzzy '${phrase}' did not resolve`);
  assert.equal(got.page, page, `fuzzy '${phrase}' -> ${got?.page}, expected ${page}`);
}
ok(`fuzzy near-miss: ${FUZZY.length} typo phrases resolve to the right page`);
// "other step" must NOT guess: no navigation, at most three options.
assert.equal(resolvePageName('go to other step'), null, "'other step' must not resolve");
const amb = unknownPageMessage('other step');
assert.match(amb, /I don't have a page called/);
assert.ok(amb.split('I can open: ')[1].split(', ').length <= 3, 'ambiguous answers list at most three');
const banana = unknownPageMessage('banana page');
assert.ok(banana.split('I can open: ')[1].split(', ').length <= 3, 'unknown pages list at most three');
assert.equal(resolvePageName('banana page'), null, "'banana page' must not resolve");
ok('ambiguous + unknown pages: no guess, at most three options');

console.log(`\n${passed} checks passed${process.exitCode ? ' (with failures)' : ''}`);
