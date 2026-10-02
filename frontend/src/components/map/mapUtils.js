// Factory-map helpers (Phase 1). Deterministic only — the abnormal check
// mirrors backend/services/abnormality.py thresholds and is labeled
// rule-based wherever it drives styling.
export const DEFAULT_THRESHOLDS = {
  temp_max: 85,
  vibration_max: 5,
  current_max: 10,
  rpm_min: 1300,
};

// Stale telemetry: grey node when the latest reading is older than this.
export const STALE_MS = 90 * 1000;

export const GRID = 20;

export function machineCode(name) {
  const m = /^M-\d{3}/.exec(name || '');
  return m ? m[0] : null;
}

export function thresholdsFor(profile, machineType) {
  const sets = (profile && profile.thresholds) || {};
  const cand = sets[machineType] || sets._default || {};
  return {
    temp_max: Number(cand.temp_max ?? DEFAULT_THRESHOLDS.temp_max),
    vibration_max: Number(cand.vibration_max ?? DEFAULT_THRESHOLDS.vibration_max),
    current_max: Number(cand.current_max ?? DEFAULT_THRESHOLDS.current_max),
    rpm_min: Number(cand.rpm_min ?? DEFAULT_THRESHOLDS.rpm_min),
  };
}

// Rule-based abnormal check (same rules as the backend detector).
export function abnormalBreaches(reading, th) {
  const breaches = [];
  if (!reading) return breaches;
  if (reading.temperature != null && reading.temperature > th.temp_max) breaches.push('temperature');
  if (reading.vibration != null && reading.vibration > th.vibration_max) breaches.push('vibration');
  if (reading.current != null && reading.current > th.current_max) breaches.push('current');
  if (reading.rpm != null && reading.rpm < th.rpm_min) breaches.push('rpm');
  const st = (reading.machine_status || '').toUpperCase();
  if (st === 'MAINTENANCE' || st === 'STOPPED') breaches.push('machine_status');
  return breaches;
}

export function readingAgeMs(reading, nowMs) {
  if (!reading || !reading.timestamp) return null;
  const t = new Date(reading.timestamp).getTime();
  if (Number.isNaN(t)) return null;
  return nowMs - t;
}

// Node visual state. Precedence: open incident > rule-based abnormal >
// stale/no data > ok. `stale` renders grey; everything else follows data.
export function nodeState(machine, latest, openIncidentCount, th, nowMs) {
  const age = readingAgeMs(latest, nowMs);
  if (openIncidentCount > 0) return { tone: 'bad', label: `${openIncidentCount} open incident(s)`, alert: true };
  const breaches = abnormalBreaches(latest, th);
  if (breaches.length > 0) return { tone: 'bad', label: `Rule-based abnormal: ${breaches.join(', ')}`, alert: true };
  if (age === null || age > STALE_MS) return { tone: 'stale', label: age === null ? 'No readings yet' : 'Stale readings', alert: false };
  return { tone: 'ok', label: 'Normal', alert: false };
}

export function snap(v, grid = GRID) {
  return Math.round(v / grid) * grid;
}

export function clamp(v, lo, hi) {
  return Math.min(hi, Math.max(lo, v));
}

// Merge saved layout with the live fleet. Machines without a saved position
// get an auto-placed slot in a default "Unassigned" zone so they always appear.
export function resolveLayout(savedLayout, machines) {
  const base = savedLayout && typeof savedLayout === 'object' ? savedLayout : {};
  const width = Number(base.width) || 1000;
  const height = Number(base.height) || 600;
  const zones = Array.isArray(base.zones) && base.zones.length > 0
    ? base.zones.map((z) => ({ ...z }))
    : [{ id: 'default', name: 'Floor', x: 20, y: 20, w: width - 40, h: height - 40 }];
  const saved = (base.machines && typeof base.machines === 'object' ? base.machines : {});
  let overflow = zones.find((z) => z.id === 'unassigned');
  if (!overflow) {
    overflow = { id: 'unassigned', name: 'Unassigned', x: width - 220, y: 20, w: 200, h: height - 40, auto: true };
  }
  const positions = {};
  const missing = [];
  for (const m of machines) {
    const code = machineCode(m.name) || m.id;
    const s = saved[code] || saved[m.name];
    if (s && Number.isFinite(Number(s.x)) && Number.isFinite(Number(s.y))) {
      positions[code] = { x: clamp(Number(s.x), 0, width), y: clamp(Number(s.y), 0, height), zone_id: s.zone_id || null, saved: true };
    } else {
      missing.push({ code, machine: m });
    }
  }
  if (missing.length > 0 && !zones.some((z) => z.id === 'unassigned')) {
    zones.push(overflow);
  }
  const zone = zones.find((z) => z.id === 'unassigned') || zones[0];
  missing.forEach((entry, i) => {
    const cols = Math.max(1, Math.floor(zone.w / 120));
    const col = i % cols;
    const row = Math.floor(i / cols);
    positions[entry.code] = {
      x: clamp(zone.x + 60 + col * 120, 0, width),
      y: clamp(zone.y + 60 + row * 90, 0, height),
      zone_id: zone.id,
      saved: false,
    };
  });
  return { width, height, zones, positions };
}

export function typeGlyph(machineType) {
  const t = (machineType || '').toLowerCase();
  if (t.includes('press')) return '▣';
  if (t.includes('robot')) return '◈';
  if (t.includes('laser')) return '✦';
  if (t.includes('weld')) return '⚡';
  if (t.includes('grind')) return '◉';
  if (t.includes('mold')) return '⬢';
  return '⚙';
}
