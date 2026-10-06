const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function fetchMachines() {
  const res = await fetch(`${API_BASE}/api/machines`);
  if (!res.ok) throw new Error(`Failed to fetch machines: ${res.status}`);
  return res.json();
}

export async function createMachine(machine) {
  const res = await fetch(`${API_BASE}/api/machines`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(machine),
  });
  if (!res.ok) throw new Error(`Failed to create machine: ${res.status}`);
  return res.json();
}

export async function postTelemetry(payload) {
  const res = await fetch(`${API_BASE}/api/telemetry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to post telemetry: ${res.status}`);
  return res.json();
}

export async function healthCheck() {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error('Backend offline');
  return res.json();
}

export async function fetchFactories() {
  const res = await fetch(`${API_BASE}/api/factories`);
  if (!res.ok) return { factories: [] };
  return res.json();
}
