import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import FactoryFloor from './components/FactoryFloor';
import MachinePanel from './components/MachinePanel';
import TransmissionStatus from './components/TransmissionStatus';
import FleetSummary from './components/FleetSummary';
import { fetchMachines, createMachine, postTelemetry, healthCheck, fetchFactories } from './services/api';
import { DEMO_MACHINES, machineCode } from './config/machines';
import { assessHealth } from './utils/health';
import './App.css';

const TELEMETRY_INTERVAL = 10000; // 10 seconds

let loadInFlight = null;

// Load machines and idempotently seed missing fleet members.
// Stable identity is the M-00X code parsed from the machine name:
// only codes absent from GET /api/machines are POSTed, so repeated
// startups never create duplicates and existing records are kept.
async function doLoadMachines({ setMachines, setSelectedId, setBackendOnline }) {
  try {
    await healthCheck();

    let [existing, factoriesData] = await Promise.all([
      fetchMachines(),
      fetchFactories().catch(() => ({ factories: [] })),
    ]);

    const factoryMap = {};
    let defaultFactoryName = 'CNC / Mechanical';
    (factoriesData?.factories || []).forEach((f) => {
      factoryMap[f.id] = f.name || f.industry;
      if (f.is_default && (f.name || f.industry)) defaultFactoryName = f.name || f.industry;
    });

    const haveCodes = new Set(existing.map((m) => machineCode(m.name)));

    for (const demo of DEMO_MACHINES) {
      if (haveCodes.has(demo.code)) continue;
      try {
        const { baseline, abnormal, position, code, ...machineData } = demo;
        const m = await createMachine(machineData);
        existing = [...existing, m];
        haveCodes.add(demo.code);
      } catch (err) {
        console.error(`Seed ${demo.code} failed:`, err);
      }
    }

    // Merge backend machines with fleet baseline/abnormal configs by code.
    const merged = existing.map((m, idx) => {
      const demo = DEMO_MACHINES.find((d) => d.code === machineCode(m.name))
        || DEMO_MACHINES[idx]
        || DEMO_MACHINES[0];
      const company = m.company_name
        || (m.factory_id ? factoryMap[m.factory_id] : null)
        || demo.company_name
        || defaultFactoryName;
      return {
        ...m,
        company_name: company,
        baseline: demo.baseline,
        abnormal: demo.abnormal,
        position: demo.position || { row: Math.floor(idx / 4), col: idx % 4 },
      };
    });
    // Stable fleet order: M-001 … M-008 first, extras last.
    merged.sort((a, b) => {
      const order = (m) => {
        const i = DEMO_MACHINES.findIndex((d) => d.code === machineCode(m.name));
        return i === -1 ? DEMO_MACHINES.length : i;
      };
      return order(a) - order(b);
    });
    setMachines(merged);
    setSelectedId(prev => prev ?? (merged.length > 0 ? merged[0].id : null));
    setBackendOnline(true);
    return true;
  } catch (err) {
    console.error('Load machines error:', err);
    setBackendOnline(false);
    return false;
  }
}

function addNoise(value, range) {
  return value + (Math.random() - 0.5) * 2 * range;
}

export default function App() {
  const [machines, setMachines] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [sensorOverrides, setSensorOverrides] = useState({});
  const [transmissionLog, setTransmissionLog] = useState([]);
  const [backendOnline, setBackendOnline] = useState(false);
  const [countdown, setCountdown] = useState(TELEMETRY_INTERVAL / 1000);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef(null);
  const countdownRef = useRef(null);
  const machinesRef = useRef([]);
  machinesRef.current = machines;

  // Module-level guard: React StrictMode double-mounts in dev, which would
  // run two concurrent loads and POST duplicate machines. Concurrent
  // callers share a single in-flight load instead.
  const loadMachines = useCallback(() => {
    if (!loadInFlight) {
      loadInFlight = doLoadMachines({
        setMachines,
        setSelectedId,
        setBackendOnline,
      }).finally(() => {
        loadInFlight = null;
      });
    }
    return loadInFlight;
  }, []);

  // Initial load only controls the loading screen; retries happen in the
  // transmission loop below so no page reload is ever required.
  useEffect(() => {
    async function init() {
      await loadMachines();
      setLoading(false);
    }
    init();
  }, [loadMachines]);

  // Get the current sensor values for a machine (override or baseline + noise)
  const getSensorValues = useCallback((machine) => {
    const override = sensorOverrides[machine.id];
    const base = machine.baseline || { temperature: 60, vibration: 2, current: 8, rpm: 1400 };

    return {
      temperature: override?.temperature ?? parseFloat(addNoise(base.temperature, 3).toFixed(1)),
      vibration: override?.vibration ?? parseFloat(addNoise(base.vibration, 0.5).toFixed(2)),
      current: override?.current ?? parseFloat(addNoise(base.current, 1).toFixed(1)),
      rpm: override?.rpm ?? Math.round(addNoise(base.rpm, 50)),
      machine_status: override?.machine_status ?? 'RUNNING',
    };
  }, [sensorOverrides]);

  // Telemetry transmission loop. Reuses the single 10s timer: if no machines
  // are loaded yet (backend was offline at startup), each tick retries the
  // machine fetch instead of transmitting. No aggressive retry loop.
  useEffect(() => {
    async function transmit() {
      // Retry machine fetch when the list is still empty.
      if (machinesRef.current.length === 0) {
        await loadMachines();
        if (machinesRef.current.length === 0) {
          setCountdown(TELEMETRY_INTERVAL / 1000);
          return;
        }
      }

      const now = new Date();
      const results = [];

      for (const machine of machinesRef.current) {
        const values = getSensorValues(machine);
        const payload = {
          machine_id: machine.id,
          temperature: values.temperature,
          vibration: values.vibration,
          current: values.current,
          rpm: values.rpm,
          machine_status: values.machine_status,
          timestamp: now.toISOString(),
        };

        try {
          await postTelemetry(payload);
          results.push({ machineId: machine.id, name: machine.name, time: now, success: true });
          setBackendOnline(true);
        } catch (err) {
          results.push({ machineId: machine.id, name: machine.name, time: now, success: false, error: err.message });
          setBackendOnline(false);
        }
      }
      setTransmissionLog(results);
      setCountdown(TELEMETRY_INTERVAL / 1000);
    }

    // Transmit immediately on start
    transmit();

    intervalRef.current = setInterval(transmit, TELEMETRY_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [loadMachines, getSensorValues]);

  // Countdown timer
  useEffect(() => {
    countdownRef.current = setInterval(() => {
      setCountdown(prev => (prev > 0 ? prev - 1 : TELEMETRY_INTERVAL / 1000));
    }, 1000);
    return () => clearInterval(countdownRef.current);
  }, []);

  const selectedMachine = machines.find(m => m.id === selectedId);

  // Effective (pinned or baseline-exact) values per machine, used for the
  // health dots and fleet summary. Live machines report exact baselines,
  // so they stay GOOD; pinned abnormal values surface as WARNING/CRITICAL.
  const effectiveById = useMemo(() => {
    const map = {};
    for (const m of machines) {
      const override = sensorOverrides[m.id];
      const base = m.baseline || { temperature: 60, vibration: 2, current: 8, rpm: 1400 };
      map[m.id] = {
        temperature: override?.temperature ?? base.temperature,
        vibration: override?.vibration ?? base.vibration,
        current: override?.current ?? base.current,
        rpm: override?.rpm ?? base.rpm,
        machine_status: override?.machine_status ?? 'RUNNING',
      };
    }
    return map;
  }, [machines, sensorOverrides]);

  const healthById = useMemo(() => {
    const map = {};
    for (const m of machines) {
      map[m.id] = assessHealth(m.baseline, effectiveById[m.id]);
    }
    return map;
  }, [machines, effectiveById]);

  const handleOverride = (machineId, newValues) => {
    setSensorOverrides(prev => ({
      ...prev,
      [machineId]: { ...prev[machineId], ...newValues },
    }));
  };

  // Per-machine independent clear: drops the pinned override so the
  // machine returns to live baseline + noise. Other machines unaffected.
  const handleClearOverride = (machineId) => {
    setSensorOverrides(prev => {
      const next = { ...prev };
      delete next[machineId];
      return next;
    });
  };

  if (loading) {
    return (
      <div className="app-loading">
        <div className="spinner" />
        <p>Connecting to backend...</p>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>🏭 IndAI IoT Simulator</h1>
        <span className="app-subtitle">Factory Floor Simulation</span>
      </header>

      <div className="app-body">
        <div className="left-panel">
          <FleetSummary
            machines={machines}
            effectiveById={effectiveById}
            backendOnline={backendOnline}
          />
          <FactoryFloor
            machines={machines}
            selectedId={selectedId}
            onSelect={setSelectedId}
            effectiveById={effectiveById}
            healthById={healthById}
          />
          <TransmissionStatus
            backendOnline={backendOnline}
            transmissionLog={transmissionLog}
            countdown={countdown}
          />
        </div>

        <div className="right-panel">
          {selectedMachine ? (
            <MachinePanel
              machine={selectedMachine}
              sensorValues={sensorOverrides[selectedMachine.id] || {}}
              baseline={selectedMachine.baseline}
              abnormal={selectedMachine.abnormal}
              onApply={(values) => handleOverride(selectedMachine.id, values)}
              onReset={() => handleClearOverride(selectedMachine.id)}
            />
          ) : (
            <div className="no-selection">
              <p>
                {machines.length === 0
                  ? 'Backend offline — waiting for machines. They will appear automatically when the backend is reachable.'
                  : 'Select a machine from the factory floor'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
