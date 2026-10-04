import { useCallback, useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import Dashboard from './pages/Dashboard';
import FactoryMap from './pages/FactoryMap';
import Employees from './pages/Employees';
import Machines from './pages/Machines';
import Orders from './pages/Orders';
import Tasks from './pages/Tasks';
import Production from './pages/Production';
import IoTMonitoring from './pages/IoTMonitoring';
import Simulator from './pages/Simulator';
import Incidents from './pages/Incidents';
import FactoryProfile from './pages/FactoryProfile';
import Import from './pages/Import';
import Memory from './pages/Memory';
import Reports from './pages/Reports';
import Plans from './pages/Plans';
import Simulate from './pages/Simulate';
import Assistant from './pages/Assistant';
import Jarvis from './pages/Jarvis';
import VoiceProvider from './components/voice/VoiceContext';
import MiniPlayer from './components/voice/MiniPlayer';
import { CommandFeedProvider, ToastHost } from './components/voice/CommandFeed';
import Users from './pages/Users';
import Login from './pages/Login';
import Onboarding from './pages/Onboarding';
import PlaceholderPage from './pages/PlaceholderPage';
import { useSystemStatus } from './hooks/useSystemStatus';
import { NAV_ITEMS, NAV_SECTIONS } from './config/nav';
import { api } from './services/api';
import { accessToken, signOut } from './services/auth';
import './App.css';

const TITLES = {  dashboard: { title: 'Command Center', subtitle: 'Factory-wide operations at a glance' },
  map: { title: 'Factory Map', subtitle: 'Floor plan and navigation' },
  profile: { title: 'Factory Profile', subtitle: 'Setup, machines and alert limits' },
  import: { title: 'Import', subtitle: 'Excel/CSV into IndAI tables' },
  employees: { title: 'Employees', subtitle: 'Workforce overview' },
  tasks: { title: 'Tasks', subtitle: 'Assignments and progress' },
  machines: { title: 'Machines', subtitle: 'Equipment and health' },
  orders: { title: 'Orders', subtitle: 'Customer demand and deadlines' },
  production: { title: 'Production', subtitle: 'Runs and output' },
  iot: { title: 'IoT Monitoring', subtitle: 'Live machine telemetry' },
  simulator: { title: 'Floor Simulator', subtitle: 'Demo telemetry for testing' },
  incidents: { title: 'Incidents', subtitle: 'Abnormal-telemetry alerts and maintenance' },
  memory: { title: 'Factory Memory', subtitle: 'Past events and admin decisions' },
  reports: { title: 'Reports', subtitle: 'Weekly summary for reviews' },
  plans: { title: 'Work Plans', subtitle: 'Draft, assign, dispatch' },
  simulate: { title: 'What-If', subtitle: 'Project decisions safely' },
  users: { title: 'Users', subtitle: 'Accounts and roles' },
  ai: { title: 'AI Assistant', subtitle: 'Administrative intelligence' },
  jarvis: { title: 'Jarvis', subtitle: 'Realtime voice agent' },
};

function readTheme() {
  try {
    return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

function readSidebarCollapsed() {
  try {
    return window.localStorage.getItem('indai.sidebar.collapsed') === '1';
  } catch {
    return false;
  }
}

export default function App() {
  // DEV ONLY: VITE_AUTH_DISABLED=true skips the login screen entirely.
  const devMode = import.meta.env.VITE_AUTH_DISABLED === 'true';
  const [route, setRoute] = useState('dashboard');
  // Optional cross-page navigation payload (Phase 1 map links), e.g.
  // navigate('orders', { orderId }). Manual nav clears it. No router.
  const [navPayload, setNavPayload] = useState(null);
  const [collapsed, setCollapsed] = useState(readSidebarCollapsed);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [theme, setTheme] = useState(readTheme);
  const toggleTheme = useCallback(() => {
    setTheme((t) => {
      const next = t === 'dark' ? 'light' : 'dark';
      try {
        document.documentElement.dataset.theme = next;
        window.localStorage.setItem('indai.theme', next);
      } catch { /* private mode: state just won't persist */ }
      return next;
    });
  }, []);
  const toggleCollapsed = useCallback(() => {
    setCollapsed((c) => {
      try {
        window.localStorage.setItem('indai.sidebar.collapsed', c ? '0' : '1');
      } catch { /* private mode: state just won't persist */ }
      return !c;
    });
  }, []);
  const navigate = useCallback((next, payload = null) => {
    setNavPayload(payload);
    setRoute(next);
  }, []);
  const handleNavigate = useCallback((next) => {
    setNavPayload(null);
    setRoute(next);
    setDrawerOpen(false);
  }, []);

  // Browser RPC "ui.command" from the voice agent (Part D). Already
  // validated; resolves human refs (codes/numbers) to ids, then navigates.
  const handleUiCommand = useCallback(async (action, args) => {
    if (action === 'navigate') {
      if (!NAV_ITEMS.some((n) => n.id === args.page)) return `rejected: unknown page '${args.page}'`;
      navigate(args.page);
      return 'ok';
    }
    if (action === 'select_machine') {
      const fleet = await api.machines();
      const want = args.machine.trim().toLowerCase();
      const hit = (Array.isArray(fleet) ? fleet : []).find((m) =>
        (m.name || '').toLowerCase().startsWith(want) || m.id === args.machine);
      if (!hit) return `rejected: no machine '${args.machine}'`;
      navigate('machines', { machineId: hit.id });
      return 'ok';
    }
    if (action === 'open_order' || action === 'focus_order_on_map') {
      const list = await api.orders();
      const want = args.order.trim().toLowerCase();
      const hit = (Array.isArray(list) ? list : []).find((o) =>
        (o.order_number || '').toLowerCase() === want || o.id === args.order);
      if (!hit) return `rejected: no order '${args.order}'`;
      if (action === 'open_order') navigate('orders', { orderId: hit.id });
      else navigate('map', { orderId: hit.id });
      return 'ok';
    }
    if (action === 'open_incident') {
      const list = await api.incidents();
      const want = args.incident.trim().toLowerCase();
      const hit = (Array.isArray(list) ? list : []).find((i) =>
        String(i.id).toLowerCase().startsWith(want));
      if (!hit) return `rejected: no incident '${args.incident}'`;
      navigate('incidents', { incidentId: hit.id });
      return 'ok';
    }
    if (action === 'show_proposals') {
      navigate('ai');
      return 'ok';
    }
    return 'rejected: unhandled';
  }, [navigate]);
  const [session, setSession] = useState(() => (devMode || !!accessToken()));
  const [user, setUser] = useState(null);
  const [gate, setGate] = useState('checking'); // checking | onboarding | ready
  const [authError, setAuthError] = useState('');
  const systemStatus = useSystemStatus();
  const meta = TITLES[route] || { title: NAV_ITEMS.find((n) => n.id === route)?.label || route };

  const checkProfile = async () => {
    try {
      const p = await api.profile();
      if (!p || p.status !== 'APPROVED') setGate('onboarding');
      else setGate('ready');
    } catch (err) {
      if (err.code === 'UNAUTHENTICATED') return; // session gate handles it
      const msg = String(err?.message || '');
      if (msg.includes('404') || msg.includes('No factory profile')) setGate('onboarding');
      else if (msg.includes('factory_profile table missing') || msg.includes('500')) setGate('onboarding');
      else setGate('ready'); // backend offline/total failure: don't block existing users
    }
  };

  const loadMe = useCallback(async () => {
    setAuthError('');
    try {
      const me = await api.me();
      setUser(me);
      // Workers use the mobile app, not this web console.
      if (me.role !== 'WORKER') checkProfile();
      return me;
    } catch (err) {
      if (err.code === 'UNAUTHENTICATED') {
        signOut();
        setSession(false);
        setUser(null);
      } else {
        setAuthError(err.message || 'Failed to load account');
      }
      return null;
    }
  }, []);

  useEffect(() => {
    if (session) loadMe();
    const onAuth = () => {
      if (accessToken()) {
        setSession(true);
        loadMe();
      } else {
        setSession(false);
        setUser(null);
      }
    };
    window.addEventListener('indai-auth', onAuth);
    return () => window.removeEventListener('indai-auth', onAuth);
  }, [session, loadMe]);

  const handleSignOut = () => {
    signOut();
    setSession(false);
    setUser(null);
    setRoute('dashboard');
  };

  if (!session || (!devMode && !accessToken())) {
    return <Login onDone={() => { setSession(true); loadMe(); }} />;
  }

  if (!user) {
    return (
      <div className="shell"><div className="main"><div className="page">
        {authError ? (
          <div className="alert-banner" role="alert">{authError}{' '}
            <button type="button" className="btn-small" onClick={loadMe}>Retry</button>{' '}
            <button type="button" className="btn-small" onClick={handleSignOut}>Sign out</button>
          </div>
        ) : <p className="muted">Loading your account…</p>}
      </div></div></div>
    );
  }

  if (user.role === 'WORKER') {
    return (
      <div className="shell"><div className="main"><div className="page" style={{ maxWidth: 520, margin: '8vh auto 0' }}>
        <div className="page-head"><div>
          <h2>IndAI worker access is mobile-only</h2>
          <p className="page-desc">Signed in as {user.email} (WORKER). Your tasks live in the IndAI worker app on your phone — this web console is for managers and operators.</p>
        </div></div>
        <button type="button" className="btn-secondary" onClick={handleSignOut}>Sign out</button>
      </div></div></div>
    );
  }

  if (gate === 'checking') {
    return (
      <div className="shell"><div className="main"><div className="page"><p className="muted">Loading factory setup…</p></div></div></div>
    );
  }

  if (gate === 'onboarding') {
    return (
      <div className="shell">
        <div className="main">
          <Topbar title="Factory setup" subtitle="First-time configuration" systemStatus={systemStatus} user={user} onSignOut={devMode ? null : handleSignOut} onNavigate={handleNavigate} />
          <Onboarding onDone={() => { setGate('ready'); setRoute('dashboard'); }} />
        </div>
      </div>
    );
  }

  // Guard: never render a nav item the role may not see.
  const allowed = NAV_ITEMS.some((n) => n.id === route && (!n.roles || n.roles.includes(user.role)));
  const shown = allowed ? route : 'dashboard';
  const crumb = NAV_SECTIONS.find((s) => s.ids.includes(shown))?.label || '';

  return (
    <VoiceProvider onUiCommand={handleUiCommand}>
    <CommandFeedProvider>
    <div className={`shell${collapsed ? ' rail' : ''}`}>
      <Sidebar active={shown} onNavigate={handleNavigate} role={user.role}
        collapsed={collapsed} onToggleCollapse={toggleCollapsed}
        drawerOpen={drawerOpen} onCloseDrawer={() => setDrawerOpen(false)} />
      <div className="main">
        <Topbar title={(TITLES[shown] || meta).title} subtitle={(TITLES[shown] || meta).subtitle} crumb={crumb} systemStatus={systemStatus} user={user} onSignOut={devMode ? null : handleSignOut} onNavigate={handleNavigate} onMenu={() => setDrawerOpen(true)} theme={theme} onToggleTheme={toggleTheme} />
        {shown === 'dashboard' ? (
          <Dashboard />
        ) : shown === 'map' ? (
          <FactoryMap onNavigate={navigate} focusOrderId={navPayload?.orderId} />
        ) : shown === 'profile' ? (
          <FactoryProfile />
        ) : shown === 'import' ? (
          <Import />
        ) : shown === 'employees' ? (
          <Employees />
        ) : shown === 'machines' ? (
          <Machines focusMachineId={navPayload?.machineId} />
        ) : shown === 'orders' ? (
          <Orders focusOrderId={navPayload?.orderId} />
        ) : shown === 'tasks' ? (
          <Tasks onNavigate={navigate} />
        ) : shown === 'production' ? (
          <Production />
        ) : shown === 'iot' ? (
          <IoTMonitoring focusMachineId={navPayload?.machineId} />
        ) : shown === 'simulator' ? (
          <Simulator />
        ) : shown === 'incidents' ? (
          <Incidents focusIncidentId={navPayload?.incidentId} />
        ) : shown === 'memory' ? (
          <Memory />
        ) : shown === 'reports' ? (
          <Reports />
        ) : shown === 'plans' ? (
          <Plans onNavigate={navigate} />
        ) : shown === 'simulate' ? (
          <Simulate />
        ) : shown === 'ai' ? (
          <Assistant />
        ) : shown === 'jarvis' ? (
          <Jarvis />
        ) : shown === 'users' ? (
          <Users me={user} />
        ) : (
          <PlaceholderPage page={shown} />
        )}
      </div>
      <MiniPlayer hidden={shown === 'jarvis'} onOpenJarvis={() => handleNavigate('jarvis')} />
    </div>
    <ToastHost />
    </CommandFeedProvider>
    </VoiceProvider>
  );
}
