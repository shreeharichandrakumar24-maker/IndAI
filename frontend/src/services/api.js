const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Reusable helper for all FastAPI calls. Never scatters fetch() across
// components. Throws on HTTP errors and on timeout (Supabase cold starts
// can be slow, so the default timeout is generous).
// Phase 1: attaches the Supabase access token when present. A 401 marks the
// session invalid so the app can return to the login screen.
async function request(path, { timeout = 30000, method = 'GET', body } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  let token = null;
  try {
    const mod = await import('./auth');
    token = mod.accessToken();
  } catch { /* auth module unavailable in tests */ }
  try {
    const headers = body !== undefined ? { 'Content-Type': 'application/json' } : {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}${path}`, {
      signal: ctrl.signal,
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let detail = '';
      try {
        const errJson = await res.json();
        detail = errJson.detail ? `: ${JSON.stringify(errJson.detail)}` : '';
      } catch { /* non-JSON error body */ }
      const err = new Error(`API ${res.status} on ${path}${detail}`);
      if (res.status === 401) err.code = 'UNAUTHENTICATED';
      if (res.status === 403) err.code = 'FORBIDDEN';
      throw err;
    }
    return res.json();
  } catch (err) {
    if (err.name === 'AbortError') throw new Error(`API timeout on ${path}`);
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

// Existing backend endpoints only. No new endpoints required.
export const api = {
  health: () => request('/api/health'),
  healthDb: () => request('/api/health/db'),
  employees: () => request('/api/employees'),
  employee: (id) => request(`/api/employees/${id}`),
  createEmployee: (data) => request('/api/employees', { method: 'POST', body: data }),
  updateEmployee: (id, data) => request(`/api/employees/${id}`, { method: 'PUT', body: data }),
  deleteEmployee: (id) => request(`/api/employees/${id}`, { method: 'DELETE' }),
  machines: () => request('/api/machines'),
  machine: (id) => request(`/api/machines/${id}`),
  createMachine: (data) => request('/api/machines', { method: 'POST', body: data }),
  updateMachine: (id, data) => request(`/api/machines/${id}`, { method: 'PUT', body: data }),
  deleteMachine: (id) => request(`/api/machines/${id}`, { method: 'DELETE' }),
  orders: () => request('/api/orders'),
  order: (id) => request(`/api/orders/${id}`),
  createOrder: (data) => request('/api/orders', { method: 'POST', body: data }),
  updateOrder: (id, data) => request(`/api/orders/${id}`, { method: 'PUT', body: data }),
  deleteOrder: (id) => request(`/api/orders/${id}`, { method: 'DELETE' }),
  tasks: () => request('/api/tasks'),
  tasksByOrder: (orderId) => request(`/api/tasks?order_id=${orderId}`),
  createTask: (data) => request('/api/tasks', { method: 'POST', body: data }),
  updateTask: (id, data) => request(`/api/tasks/${id}`, { method: 'PUT', body: data }),
  deleteTask: (id) => request(`/api/tasks/${id}`, { method: 'DELETE' }),
  production: () => request('/api/production'),
  productionRun: (id) => request(`/api/production/${id}`),
  createProduction: (data) => request('/api/production', { method: 'POST', body: data }),
  updateProduction: (id, data) => request(`/api/production/${id}`, { method: 'PUT', body: data }),
  deleteProduction: (id) => request(`/api/production/${id}`, { method: 'DELETE' }),
  incidents: () => request('/api/incidents'),
  incident: (id) => request(`/api/incidents/${id}`),
  createIncident: (data) => request('/api/incidents', { method: 'POST', body: data }),
  updateIncident: (id, data) => request(`/api/incidents/${id}`, { method: 'PUT', body: data }),
  deleteIncident: (id) => request(`/api/incidents/${id}`, { method: 'DELETE' }),
  maintenanceList: () => request('/api/maintenance'),
  maintenance: (id) => request(`/api/maintenance/${id}`),
  maintenanceByMachine: (machineId) => request(`/api/maintenance?machine_id=${machineId}`),
  createMaintenance: (data) => request('/api/maintenance', { method: 'POST', body: data }),
  updateMaintenance: (id, data) => request(`/api/maintenance/${id}`, { method: 'PUT', body: data }),
  deleteMaintenance: (id) => request(`/api/maintenance/${id}`, { method: 'DELETE' }),
  checkMachine: (machineId) => request(`/api/telemetry/${machineId}/check`, { method: 'POST' }),
  postTelemetry: (payload) => request('/api/telemetry', { method: 'POST', body: payload }),
  checkAllMachines: () => request('/api/telemetry/check-all', { method: 'POST' }),
  machineHealth: (machineId) => request(`/api/telemetry/${machineId}/health-check`),
  machineTelemetry: (machineId, limit = 20) =>
    request(`/api/machines/${machineId}/telemetry?limit=${limit}`),
  // Canonical telemetry endpoints (same records the simulator POSTs).
  telemetry: (machineId, limit = 20) =>
    request(`/api/telemetry/${machineId}?limit=${limit}`),
  latestTelemetry: async (machineId) => {
    // NOTE: GET /api/telemetry/latest/{id} is shadowed by the earlier
    // /{machine_id} route in the backend router ("latest" fails UUID
    // validation), so latest is read as limit=1 of the newest-first list.
    const rows = await request(`/api/telemetry/${machineId}?limit=1`);
    return Array.isArray(rows) && rows.length > 0 ? rows[0] : null;
  },
  // Factory profile / onboarding (Phase A-B).
  profile: () => request('/api/profile'),
  presetProfile: () => request('/api/profile/preset'),
  generateProfile: (answers) => request('/api/profile/generate', { method: 'POST', body: { answers } }),
  saveProfile: (profile) => request('/api/profile', { method: 'PUT', body: { profile } }),
  approveProfile: () => request('/api/profile/approve', { method: 'POST' }),
  // CSV/Excel import (Phase C) — multipart, separate from JSON request().
  analyzeImport: async (target, file) => {
    const { accessToken } = await import('./auth');
    const fd = new FormData();
    fd.append('target', target);
    fd.append('file', file);
    const headers = {};
    const t = accessToken();
    if (t) headers.Authorization = `Bearer ${t}`;
    const res = await fetch(`${API_BASE}/api/import/analyze`, { method: 'POST', headers, body: fd });
    if (!res.ok) {
      let detail = '';
      try { const j = await res.json(); detail = j.detail ? `: ${JSON.stringify(j.detail)}` : ''; } catch { /* ignore */ }
      throw new Error(`API ${res.status} on /api/import/analyze${detail}`);
    }
    return res.json();
  },
  commitImport: async (target, file, mapping) => {
    const { accessToken } = await import('./auth');
    const fd = new FormData();
    fd.append('target', target);
    fd.append('mapping', JSON.stringify(mapping));
    fd.append('file', file);
    const headers = {};
    const t = accessToken();
    if (t) headers.Authorization = `Bearer ${t}`;
    const res = await fetch(`${API_BASE}/api/import/commit`, { method: 'POST', headers, body: fd });
    if (!res.ok) {
      let detail = '';
      try { const j = await res.json(); detail = j.detail ? `: ${JSON.stringify(j.detail)}` : ''; } catch { /* ignore */ }
      throw new Error(`API ${res.status} on /api/import/commit${detail}`);
    }
    return res.json();
  },
  // AI analysis + factory memory (Phase E).
  analyzeIncident: (incidentId) => request(`/api/ai/analyze-incident/${incidentId}`, { method: 'POST' }),
  recommendations: (entityId) => request(`/api/ai/recommendations${entityId ? `?entity_id=${entityId}` : ''}`),
  decideRecommendation: (recId, decision, note) =>
    request(`/api/ai/recommendations/${recId}/decision`, { method: 'PATCH', body: { decision, note } }),
  memory: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/memory${q ? `?${q}` : ''}`);
  },
  memoryLog: (entry) => request('/api/memory/log', { method: 'POST', body: entry }),
  memorySearch: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/memory/search?${q}`);
  },
  similarMemory: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/memory/similar?${q}`);
  },
  // Users + roles (Phase 1).
  me: () => request('/api/users/me'),
  users: () => request('/api/users'),
  setUserRole: (id, role) => request(`/api/users/${id}/role`, { method: 'PUT', body: { role } }),
  updateUser: (id, data) => request(`/api/users/${id}`, { method: 'PUT', body: data }),
  // Notifications bell (Phase 2).
  notifications: (params = {}) => {
    const q = new URLSearchParams({ limit: 20, ...params }).toString();
    return request(`/api/notifications?${q}`);
  },
  unreadCount: () => request('/api/notifications/unread-count'),
  markNotificationRead: (id) => request(`/api/notifications/${id}/read`, { method: 'POST' }),
  markAllNotificationsRead: () => request('/api/notifications/read-all', { method: 'POST' }),
  // Weekly reports (Phase 5).
  // Weekly reports (Phase 5).
  weeklyReport: (weekOffset = 0) => request(`/api/reports/weekly?week_offset=${weekOffset}`),
  // AI Assistant chat (Phase 6).
  chat: (message, history = []) => request('/api/ai/chat', { method: 'POST', body: { message, history } }),
  // Jarvis assistant (mobile-app Phase 4): tool-loop chat + quick stats.
  assistantChat: (messages) => request('/api/ai/assistant/chat', { method: 'POST', body: { messages } }),
  assistantQuick: (which) => request(`/api/ai/assistant/quick/${which}`),
  // Jarvis realtime voice: SSE stream (trace/sentence/done events).
  // Uses raw fetch + reader (request() would wait for the full body).
  assistantVoice: async (messages, onEvent) => {
    const { accessToken } = await import('./auth');
    const headers = { 'Content-Type': 'application/json' };
    const t = accessToken();
    if (t) headers.Authorization = `Bearer ${t}`;
    const res = await fetch(`${API_BASE}/api/ai/assistant/voice`, {
      method: 'POST', headers, body: JSON.stringify({ messages }),
    });
    if (!res.ok) {
      let detail = '';
      try {
        const j = await res.json();
        detail = j.detail ? `: ${JSON.stringify(j.detail)}` : '';
      } catch { /* SSE error shape differs */ }
      throw new Error(`API ${res.status} on /api/ai/assistant/voice${detail}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const evMatch = chunk.match(/^event: (\w+)\ndata: ([\s\S]*)$/);
        if (evMatch) {
          try {
            onEvent(evMatch[1], JSON.parse(evMatch[2]));
          } catch { /* ignore malformed chunk */ }
        }
      }
    }
  },
  // Predictive order risk (F8).
  ordersAtRisk: (withAi = false) => request(`/api/orders/at-risk${withAi ? '?ai=true' : ''}`),
  notifyOrderRisk: (orderId) => request(`/api/orders/at-risk/notify?order_id=${orderId}`, { method: 'POST' }),
  // Cross-system root cause (F7).
  rootCause: (scope) => request('/api/ai/root-cause', { method: 'POST', body: scope }),
  // What-if simulation (F9). Display-only; applying uses normal endpoints.
  simulate: (payload) => request('/api/ai/simulate', { method: 'POST', body: payload }),
  // Smart Split (mobile-app Phase 3). Proposal only; creation is explicit.
  smartSplit: (orderId) => request('/api/ai/smart-split', { method: 'POST', body: { order_id: orderId } }),
  // Work plans + AI assignment (Phase 7 / F6).
  plans: () => request('/api/plans'),
  plan: (id) => request(`/api/plans/${id}`),
  createPlan: (data) => request('/api/plans', { method: 'POST', body: data }),
  approvePlan: (id) => request(`/api/plans/${id}/approve`, { method: 'POST' }),
  dispatchPlan: (id) => request(`/api/plans/${id}/dispatch`, { method: 'POST' }),
  planAssignments: (id) => request(`/api/plans/${id}/assignments`),
  suggestAssignments: (id) => request(`/api/plans/${id}/suggest`, { method: 'POST' }),
  pairAssignment: (id, data) => request(`/api/assignments/${id}/pair`, { method: 'PATCH', body: data }),
};

export { API_BASE };
