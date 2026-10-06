// Canonical factory fleet. `code` (M-001 … M-008) is the stable identity
// used for idempotent seeding: the simulator only POSTs demo machines
// whose code is missing from GET /api/machines, so restarts never duplicate.
export const DEMO_MACHINES = [
  {
    code: 'M-001',
    name: 'M-001 CNC Milling Machine',
    machine_type: 'CNC',
    company_name: 'CNC / Mechanical',
    location: 'Bay A - North',
    status: 'OPERATIONAL',
    health_status: 'GOOD',
    baseline: { temperature: 68, vibration: 2.0, current: 8.0, rpm: 1450 },
    abnormal: { temperature: 95, vibration: 6.5, current: 12.0, rpm: 1200 },
    position: { row: 0, col: 0 },
  },
  {
    code: 'M-002',
    name: 'M-002 CNC Turning Machine',
    machine_type: 'CNC',
    company_name: 'CNC / Mechanical',
    location: 'Bay A - South',
    status: 'OPERATIONAL',
    health_status: 'GOOD',
    baseline: { temperature: 72, vibration: 2.5, current: 9.5, rpm: 1200 },
    abnormal: { temperature: 98, vibration: 7.0, current: 14.0, rpm: 900 },
    position: { row: 0, col: 1 },
  },
  {
    code: 'M-003',
    name: 'M-003 Hydraulic Press',
    machine_type: 'Press',
    company_name: 'CNC / Mechanical',
    location: 'Bay B - Center',
    status: 'OPERATIONAL',
    health_status: 'GOOD',
    baseline: { temperature: 55, vibration: 3.5, current: 15.0, rpm: 0 },
    abnormal: { temperature: 80, vibration: 8.0, current: 22.0, rpm: 0 },
    position: { row: 0, col: 2 },
  },
  {
    code: 'M-004',
    name: 'M-004 Surface Grinder',
    machine_type: 'Grinder',
    company_name: 'CNC / Mechanical',
    location: 'Bay B - East',
    status: 'OPERATIONAL',
    health_status: 'GOOD',
    baseline: { temperature: 60, vibration: 4.0, current: 7.5, rpm: 3000 },
    abnormal: { temperature: 88, vibration: 9.5, current: 11.0, rpm: 2200 },
    position: { row: 0, col: 3 },
  },
  {
    code: 'M-005',
    name: 'M-005 Welding Station',
    machine_type: 'Welder',
    company_name: 'CNC / Mechanical',
    location: 'Bay C - West',
    status: 'OPERATIONAL',
    health_status: 'GOOD',
    baseline: { temperature: 75, vibration: 1.2, current: 18.0, rpm: 0 },
    abnormal: { temperature: 105, vibration: 4.5, current: 26.0, rpm: 0 },
    position: { row: 1, col: 0 },
  },
  {
    code: 'M-006',
    name: 'M-006 Assembly Robot',
    machine_type: 'Robot',
    company_name: 'CNC / Mechanical',
    location: 'Bay C - Center',
    status: 'OPERATIONAL',
    health_status: 'GOOD',
    baseline: { temperature: 48, vibration: 1.8, current: 5.5, rpm: 900 },
    abnormal: { temperature: 72, vibration: 5.5, current: 9.0, rpm: 600 },
    position: { row: 1, col: 1 },
  },
  {
    code: 'M-007',
    name: 'M-007 Laser Cutter',
    machine_type: 'Laser',
    company_name: 'CNC / Mechanical',
    location: 'Bay D - North',
    status: 'OPERATIONAL',
    health_status: 'GOOD',
    baseline: { temperature: 62, vibration: 1.0, current: 11.0, rpm: 0 },
    abnormal: { temperature: 90, vibration: 3.8, current: 16.0, rpm: 0 },
    position: { row: 1, col: 2 },
  },
  {
    code: 'M-008',
    name: 'M-008 Injection Molding Machine',
    machine_type: 'Molder',
    company_name: 'CNC / Mechanical',
    location: 'Bay D - South',
    status: 'OPERATIONAL',
    health_status: 'GOOD',
    baseline: { temperature: 85, vibration: 2.8, current: 13.5, rpm: 750 },
    abnormal: { temperature: 115, vibration: 7.5, current: 19.0, rpm: 500 },
    position: { row: 1, col: 3 },
  },
];

// Machine status options used for telemetry + fleet summary
export const MACHINE_STATUSES = ['RUNNING', 'IDLE', 'MAINTENANCE', 'STOPPED'];

// Extract the stable fleet code (M-001 …) from a backend machine name.
export function machineCode(name) {
  const m = /^M-\d{3}/.exec(name || '');
  return m ? m[0] : null;
}
