// Central navigation definition. Full pages for items other than
// 'dashboard' land in later phases; they render PlaceholderPage for now.
export const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'map', label: 'Factory Map', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'profile', label: 'Factory Profile', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'import', label: 'Import', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'employees', label: 'Employees', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'tasks', label: 'Tasks', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'machines', label: 'Machines', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'orders', label: 'Orders', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'production', label: 'Production', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'iot', label: 'IoT Monitoring', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'simulator', label: 'Simulator', roles: ['MANAGER'] },
  { id: 'incidents', label: 'Incidents', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'memory', label: 'Factory Memory', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'reports', label: 'Reports', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'plans', label: 'Work Plans', roles: ['MANAGER'] },
  { id: 'simulate', label: 'What-If', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'users', label: 'Users', roles: ['MANAGER'] },
  { id: 'ai', label: 'AI Assistant', roles: ['MANAGER', 'OPERATOR'] },
  { id: 'jarvis', label: 'Jarvis', roles: ['MANAGER', 'OPERATOR'] },
];

// Sidebar grouping only. Ids + labels come from NAV_ITEMS above (unchanged),
// so state-based routing in App.jsx is unaffected.
export const NAV_SECTIONS = [
  { label: 'Overview', ids: ['dashboard', 'map'] },
  { label: 'Operations', ids: ['orders', 'tasks', 'production', 'employees', 'plans'] },
  { label: 'Machines & IoT', ids: ['machines', 'iot', 'simulator', 'incidents'] },
  { label: 'Intelligence', ids: ['jarvis', 'ai', 'simulate', 'memory', 'reports'] },
  { label: 'Setup', ids: ['profile', 'import', 'users'] },
];
