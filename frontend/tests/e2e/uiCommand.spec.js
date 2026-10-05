// Headless tests for the browser side of "ui.command" (no real LiveKit):
// a dev-only bridge (window.__indaiUiCommand) runs the SAME strict validator
// and the SAME App handler the LiveKit RPC uses.
// Run from frontend/:  npx playwright test
import { test, expect } from '@playwright/test';
import { NAV_ITEMS } from '../../src/config/nav.js';

// Mirror of TITLES in App.jsx (what the topbar shows per route).
const TITLES = {
  dashboard: 'Command Center', map: 'Factory Map', profile: 'Factory Profile',
  import: 'Import', employees: 'Employees', tasks: 'Tasks', machines: 'Machines',
  orders: 'Orders', production: 'Production', iot: 'IoT Monitoring',
  simulator: 'Floor Simulator', incidents: 'Incidents', memory: 'Factory Memory',
  reports: 'Reports', plans: 'Work Plans', simulate: 'What-If', users: 'Users',
  ai: 'AI Assistant', jarvis: 'Jarvis',
};

const ME = {
  id: 'u1', name: 'QA Manager', email: 'qa@indai.test',
  role: 'MANAGER', active: true, created_at: '2026-01-01T00:00:00Z',
};

const MACHINE = {
  id: 'm1', name: 'M-001 CNC Mill', machine_type: 'CNC', status: 'OPERATIONAL',
  health_status: 'GOOD', location: 'Line 1', created_at: '2026-01-01T00:00:00Z',
};
const MACHINE2 = {
  id: 'm2', name: 'M-002 Lathe', machine_type: 'CNC', status: 'MAINTENANCE',
  health_status: 'FAIR', location: 'Line 2', created_at: '2026-01-01T00:00:00Z',
};
const EMPLOYEE = {
  id: 'e1', name: 'Anita Rao', role: 'Welder', shift: 'Morning',
  availability: 'AVAILABLE', status: 'ACTIVE', skills: { items: ['Welding'] },
  created_at: '2026-01-01T00:00:00Z',
};
const ORDER = {
  id: 'o1', order_number: 'ORD-001', customer_name: 'Acme', product: 'Gears',
  quantity: 10, priority: 'NORMAL', status: 'PENDING', deadline: '2026-12-01T00:00:00Z',
  progress: 0, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
};
const RUN = {
  id: 'r1', order_id: null, machine_id: 'm1', task_id: null, status: 'PLANNED',
  quantity_target: 10, quantity_completed: 0, created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};
const INCIDENT = {
  id: 'aaaaaaaa-1111-2222-3333-444444444444', machine_id: 'm1', order_id: null,
  status: 'OPEN', severity: 'HIGH', incident_type: 'THERMAL',
  description: 'Overheat on M-001', created_at: '2026-10-01T10:00:00Z',
  resolved_at: null,
};
const TASK = {
  id: 'bbbbbbbb-1111-2222-3333-444444444444', name: 'Weld frame',
  description: '', required_skill: 'Welding', priority: 'HIGH',
  status: 'PENDING', employee_id: null, machine_id: null, order_id: null,
  start_time: null, deadline: null, progress: 0,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z',
};

const FIXTURES = {
  '/api/users/me': ME,
  '/api/users': [ME, { ...ME, id: 'u2', role: 'OPERATOR', name: 'Op Two' }],
  '/api/profile': {
    id: 'p1', industry: 'CNC / Mechanical', status: 'APPROVED',
    source: 'preset', profile: {
      machines: [{ code: 'M-001', name: 'M-001 CNC Mill', machine_type: 'CNC' }],
      thresholds: { CNC: { temp_max: 85, vibration_max: 5, current_max: 10, rpm_min: 1300 } },
    },
  },
  '/api/machines': [MACHINE, MACHINE2],
  '/api/incidents': [INCIDENT],
  '/api/tasks': [TASK],
  '/api/orders': [ORDER],
  '/api/production': [RUN],
  '/api/employees': [EMPLOYEE],
  '/api/plans': [],
  '/api/memory': [],
  '/api/ai/proposals': [],
  '/api/ai/autonomy': { autonomy: 'FAST' },
  '/api/ai/assistant/quick/overview': { summary: '1 order, 1 machine' },
  '/api/ai/assistant/chat': { reply: 'All good.', tool_trace: [], commands: [], proposed_actions: [] },
  '/api/reports/weekly': {
    week_start: '2026-09-28', week_end: '2026-10-04',
    orders: { completed_this_week: 1, late_now: 0, active_total: 1, late_orders: [] },
    downtime: { incidents_raised_this_week: 0, currently_open: 1 },
    top_failing_machines: [], decisions: { admin_decisions_this_week: 0, recommendations_approved: 0, recommendations_rejected: 0 },
  },
  '/api/health': { status: 'ok' },
  '/api/health/db': { status: 'ok' },
  '/api/notifications/unread-count': { count: 0 },
  '/api/voice/status': { configured: false, missing: ['LIVEKIT_URL'] },
};

async function mockApi(page, { profile } = {}) {
  await page.route('http://localhost:8000/api/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/profile' && profile === 'onboarding') {
      return route.fulfill({ status: 404, json: { detail: 'No factory profile yet.' } });
    }
    if (Object.prototype.hasOwnProperty.call(FIXTURES, path)) {
      return route.fulfill({ json: FIXTURES[path] });
    }
    if (path.startsWith('/api/notifications')) return route.fulfill({ json: [] });
    if (path.includes('/telemetry')) return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: 'not mocked in test' } });
  });
}

async function cmd(page, payload) {
  return page.evaluate((p) => window.__indaiUiCommand(JSON.stringify(p)), payload);
}

async function openApp(page, opts) {
  await mockApi(page, opts);
  await page.goto('/');
  if (opts?.profile === 'onboarding') {
    await expect(page.locator('.main h1')).toHaveText('Factory setup', { timeout: 20_000 });
    return;
  }
  await expect(page.locator('nav[aria-label="Sections"] .nav-item').first()).toBeVisible({ timeout: 20_000 });
}

const activeNav = (page) => page.locator('nav[aria-label="Sections"] .nav-item.active .nav-label');
const h1 = (page) => page.locator('.main h1').first();
const selectValues = (page) => page.$$eval('select', (els) => els.map((e) => e.value));

// Polls until React has committed the preset into the page's filter state.
async function expectFilter(page, value) {
  await expect.poll(() => selectValues(page)).toContain(value);
}

test.describe('ui.command: every page', () => {
  for (const item of NAV_ITEMS) {
    test(`navigates to ${item.id} (${item.label})`, async ({ page }) => {
      await openApp(page);
      const res = await cmd(page, { action: 'navigate', page: item.id });
      expect(res).toBe('ok');
      await expect(activeNav(page)).toHaveText(item.label);
      await expect(h1(page)).toHaveText(TITLES[item.id]);
      await expect(page.locator('.main .page').first()).toBeVisible();
    });
  }
});

test.describe('ui.command: filters through existing page filter state', () => {
  test('incidents OPEN preset lands in the status filter', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'incidents', filter: 'OPEN' })).toBe('ok');
    await expect(activeNav(page)).toHaveText('Incidents');
    await expectFilter(page, 'OPEN');
  });

  test('tasks PENDING preset lands in the status filter', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'tasks', filter: 'PENDING' })).toBe('ok');
    await expectFilter(page, 'PENDING');
  });

  test('plans progress preset opens the Progress tracker tab', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'plans', filter: 'progress' })).toBe('ok');
    await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText('Progress tracker');
  });

  test('plans live preset opens the Live plan tab', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'plans', filter: 'live' })).toBe('ok');
    await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveText('Live plan');
  });

  test('map stale preset lands in the status filter', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'map', filter: 'stale' })).toBe('ok');
    await expectFilter(page, 'stale');
  });

  test('wrong filter for the page is rejected with a spoken list', async ({ page }) => {
    await openApp(page);
    const res = await cmd(page, { action: 'navigate', page: 'machines', filter: 'OPEN' });
    expect(res).toMatch(/rejected: Machines has no filter 'OPEN'/);
    await expect(h1(page)).toHaveText('Command Center'); // never moved
  });

  test('orders PENDING preset lands in the status filter', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'orders', filter: 'PENDING' })).toBe('ok');
    await expectFilter(page, 'PENDING');
  });

  test('production PLANNED preset lands in the status filter', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'production', filter: 'PLANNED' })).toBe('ok');
    await expectFilter(page, 'PLANNED');
  });

  test('machines MAINTENANCE preset lands in the status filter', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'machines', filter: 'MAINTENANCE' })).toBe('ok');
    await expectFilter(page, 'MAINTENANCE');
  });

  test('employees ACTIVE preset lands in the status filter', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'employees', filter: 'ACTIVE' })).toBe('ok');
    await expectFilter(page, 'ACTIVE');
  });
});

test.describe('ui.command: strictness', () => {
  test('unknown page: spoken answer with at most six suggestions, no navigation', async ({ page }) => {
    await openApp(page);
    const res = await cmd(page, { action: 'navigate', page: 'banana' });
    expect(res).toContain("I don't have a page called banana");
    const suggestions = res.split('I can open: ')[1].split(', ');
    expect(suggestions.length).toBeLessThanOrEqual(6);
    await expect(h1(page)).toHaveText('Command Center');
  });

  test('external URLs and script-like pages are rejected', async ({ page }) => {
    await openApp(page);
    for (const pageId of ['https://evil.com', 'http://evil.com', 'javascript:alert(1)', '<script>alert(1)</script>']) {
      const res = await cmd(page, { action: 'navigate', page: pageId });
      expect(res).toMatch(/^rejected:/);
    }
    await expect(h1(page)).toHaveText('Command Center');
  });

  test('extra fields, wrong types and unknown actions are rejected', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'machines', url: 'https://evil.com' }))
      .toMatch(/unexpected field 'url'/);
    expect(await cmd(page, { action: 'show_proposals', page: 'machines' }))
      .toMatch(/unexpected field 'page'/);
    expect(await cmd(page, { action: 'navigate', page: 42 })).toMatch(/must be a string/);
    expect(await cmd(page, { action: 'wipe_everything' })).toMatch(/unknown action/);
    const raw = await page.evaluate(() => window.__indaiUiCommand('not json {'));
    expect(raw).toMatch(/not JSON/);
    await expect(h1(page)).toHaveText('Command Center');
  });

  test('compound: open the incident for M-001 lands on the incident', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'open_incident', incident: 'M-001' })).toBe('ok');
    await expect(activeNav(page)).toHaveText('Incidents');
    await expect(page.locator('.main .page')).toContainText('Overheat on M-001');
  });
});

test.describe('ui.command: from every state', () => {
  test('from the Jarvis page (mini player hidden there)', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'jarvis' })).toBe('ok');
    await expect(h1(page)).toHaveText('Jarvis');
    expect(await cmd(page, { action: 'navigate', page: 'production' })).toBe('ok');
    await expect(h1(page)).toHaveText('Production');
    await expect(activeNav(page)).toHaveText('Production');
  });

  test('with the sidebar collapsed', async ({ page }) => {
    await openApp(page);
    await page.locator('.rail-toggle').click();
    await expect(page.locator('.shell.rail')).toBeVisible();
    expect(await cmd(page, { action: 'navigate', page: 'employees' })).toBe('ok');
    await expect(h1(page)).toHaveText('Employees');
    // Rail mode hides labels; active class must still be there.
    await expect(page.locator('nav[aria-label="Sections"] .nav-item.active')).toHaveCount(1);
  });

  test('mobile drawer: navigation closes it', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openApp(page);
    await page.locator('.hamburger').click();
    await expect(page.locator('.sidebar.drawer-open')).toBeVisible();
    expect(await cmd(page, { action: 'navigate', page: 'orders' })).toBe('ok');
    await expect(h1(page)).toHaveText('Orders');
    await expect(page.locator('.sidebar.drawer-open')).toHaveCount(0);
  });

  test('modal open: navigating away closes it', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'machines' })).toBe('ok');
    await page.locator('button:has-text("Add Machine")').click();
    await expect(page.locator('.modal-backdrop')).toBeVisible();
    expect(await cmd(page, { action: 'navigate', page: 'tasks' })).toBe('ok');
    await expect(h1(page)).toHaveText('Tasks');
    await expect(page.locator('.modal-backdrop')).toHaveCount(0);
  });

  test('modal open on the SAME page: dialog is closed, page stays', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'machines' })).toBe('ok');
    await page.locator('button:has-text("Add Machine")').click();
    await expect(page.locator('.modal-backdrop')).toBeVisible();
    expect(await cmd(page, { action: 'navigate', page: 'machines' })).toBe('ok');
    await expect(page.locator('.modal-backdrop')).toHaveCount(0);
    await expect(h1(page)).toHaveText('Machines');
  });

  test('onboarding active: polite refusal, no navigation', async ({ page }) => {
    await openApp(page, { profile: 'onboarding' });
    await expect(h1(page)).toHaveText('Factory setup');
    const res = await cmd(page, { action: 'navigate', page: 'machines' });
    expect(res).toContain("Factory setup isn't finished yet");
    await expect(h1(page)).toHaveText('Factory setup');
    await expect(page.locator('.nav-item')).toHaveCount(0);
  });
});

test.describe('typed text assistant navigation', () => {
  test('typed "open machines" navigates through the same validator', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'ai' })).toBe('ok');
    await expect(h1(page)).toHaveText('AI Assistant');
    await page.locator('input[placeholder^="Ask in plain words"]').fill('open machines');
    await page.locator('button:has-text("Send")').click();
    await expect(h1(page)).toHaveText('Machines');
    await expect(activeNav(page)).toHaveText('Machines');
  });

  test('typed question goes to the AI instead of navigating', async ({ page }) => {
    await openApp(page);
    expect(await cmd(page, { action: 'navigate', page: 'ai' })).toBe('ok');
    await page.locator('input[placeholder^="Ask in plain words"]').fill("what's happening in production?");
    await page.locator('button:has-text("Send")').click();
    await expect(page.locator('text=All good.')).toBeVisible();
    await expect(h1(page)).toHaveText('AI Assistant');
  });
});
