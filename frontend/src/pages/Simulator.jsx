import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import { DEMO_MACHINES, machineCode } from '../config/fleet';

const INTERVAL_MS = 10000;
let seedInFlight = null;

function addNoise(value, range) {
  return value + (Math.random() - 0.5) * 2 * range;
}

// In-app factory-floor simulator (manager-only). Replaces the standalone
// :5174 app for daily use: idempotent fleet seed + 10s transmit loop +
// per-machine Set Abnormal / Set Normal pins. Same API, main design language.
export default function Simulator() {
  const [machines, setMachines] = useState([]);
  const [running, setRunning] = useState(false);
  const [pins, setPins] = useState({}); // machineId -> 'abnormal' | undefined
  const [log, setLog] = useState([]);
  const [seedMsg, setSeedMsg] = useState('');
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(INTERVAL_MS / 1000);
  const machinesRef = useRef([]);
  machinesRef.current = machines;
  const pinsRef = useRef({});
  pinsRef.current = pins;
  const timerRef = useRef(null);
  const countRef = useRef(null);

  const seed = useCallback(async () => {
    if (!seedInFlight) {
      seedInFlight = (async () => {
        let existing = await api.machines();
        const have = new Set(existing.map((m) => machineCode(m.name)));
        let created = 0;
        for (const demo of DEMO_MACHINES) {
          if (have.has(demo.code)) continue;
          const { baseline, abnormal, code, ...data } = demo;
          const m = await api.createMachine(data);
          existing = [...existing, m];
          have.add(demo.code);
          created += 1;
        }
        const merged = existing.map((m) => {
          const demo = DEMO_MACHINES.find((d) => d.code === machineCode(m.name)) || DEMO_MACHINES[0];
          return { ...m, baseline: demo.baseline, abnormal: demo.abnormal };
        });
        merged.sort((a, b) => {
          const order = (m) => {
            const i = DEMO_MACHINES.findIndex((d) => d.code === machineCode(m.name));
            return i === -1 ? DEMO_MACHINES.length : i;
          };
          return order(a) - order(b);
        });
        setMachines(merged);
        setSeedMsg(`Fleet ready: ${created} seeded, ${merged.length - created} already present (idempotent).`);
      })().finally(() => { seedInFlight = null; });
    }
    return seedInFlight;
  }, []);

  useEffect(() => {
    seed().catch((err) => setError(err.message || 'Failed to load machines'));
  }, [seed]);

  const valuesFor = useCallback((machine) => {
    const pinned = pinsRef.current[machine.id] === 'abnormal';
    const base = pinned ? machine.abnormal : machine.baseline;
    return {
      temperature: +addNoise(base.temperature, pinned ? 0.5 : 3).toFixed(1),
      vibration: +addNoise(base.vibration, pinned ? 0.2 : 0.5).toFixed(2),
      current: +addNoise(base.current, pinned ? 0.3 : 1).toFixed(1),
      rpm: Math.round(addNoise(base.rpm, 50)),
      machine_status: 'RUNNING',
    };
  }, []);

  const transmit = useCallback(async () => {
    if (machinesRef.current.length === 0) {
      try { await seed(); } catch { /* retry next tick */ }
      setCountdown(INTERVAL_MS / 1000);
      return;
    }
    const now = new Date();
    const results = [];
    for (const m of machinesRef.current) {
      const v = valuesFor(m);
      try {
        await api.postTelemetry({ machine_id: m.id, ...v, timestamp: now.toISOString() });
        results.push({ id: m.id, ok: true, time: now.toLocaleTimeString() });
      } catch (err) {
        results.push({ id: m.id, ok: false, time: now.toLocaleTimeString(), error: err.message });
      }
    }
    setLog(results);
    setCountdown(INTERVAL_MS / 1000);
  }, [seed, valuesFor]);

  useEffect(() => {
    if (!running) {
      if (timerRef.current) clearInterval(timerRef.current);
      if (countRef.current) clearInterval(countRef.current);
      return;
    }
    transmit();
    timerRef.current = setInterval(transmit, INTERVAL_MS);
    countRef.current = setInterval(() => {
      setCountdown((c) => (c > 0 ? c - 1 : INTERVAL_MS / 1000));
    }, 1000);
    return () => {
      clearInterval(timerRef.current);
      clearInterval(countRef.current);
    };
  }, [running, transmit]);

  const okCount = log.filter((l) => l.ok).length;
  const pinnedCount = Object.keys(pins).length;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Floor Simulator</h2>
          <p className="page-desc">Built-in demo telemetry. Pin a machine Abnormal to test detection, then Set Normal to recover. Managers only.</p>
        </div>
        <button type="button" className={running ? 'btn-secondary' : 'btn-primary'} onClick={() => { setError(''); setRunning((r) => !r); }}>
          {running ? `⏸ Stop (next in ${countdown}s)` : '▶ Start transmitting (10s)'}
        </button>
      </div>

      <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <StatCard label="Fleet" value={machines.length} sub="machines" loading={false} />
        <StatCard label="Transmitting" value={running ? 'ON' : 'OFF'} sub={running ? `next in ${countdown}s` : 'stopped'} loading={false} />
        <StatCard label="Last batch" value={log.length ? `${okCount}/${log.length}` : '—'} sub="delivered" loading={false} />
        <StatCard label="Pinned abnormal" value={pinnedCount} sub="will raise incidents" loading={false} />
      </section>

      {error && <div className="alert-banner" role="alert">{error}</div>}
      {seedMsg && <div className="panel" role="status"><p className="muted">{seedMsg}</p></div>}

      <section className="panel">
        <h2>Machines</h2>
        <table className="data-table">
          <thead><tr><th>Code</th><th>Name</th><th>State</th><th>Pin</th></tr></thead>
          <tbody>
            {machines.map((m) => {
              const pinned = pins[m.id] === 'abnormal';
              return (
                <tr key={m.id} style={pinned ? { background: 'rgba(239,68,68,0.08)' } : undefined}>
                  <td className="cell-mono">{machineCode(m.name) || '—'}</td>
                  <td className="cell-strong">{m.name}</td>
                  <td><StatusBadge tone={pinned ? 'bad' : 'ok'}>{pinned ? 'ABNORMAL (pinned)' : 'NORMAL (baseline)'}</StatusBadge></td>
                  <td>
                    {!pinned ? (
                      <button type="button" className="btn-small" onClick={() => setPins((p) => ({ ...p, [m.id]: 'abnormal' }))}>Set Abnormal</button>
                    ) : (
                      <button type="button" className="btn-small" onClick={() => setPins((p) => { const n = { ...p }; delete n[m.id]; return n; })}>Set Normal</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="muted" style={{ marginTop: 8 }}>Some baselines (press/welder/laser current, low-RPM machines) exceed default alert limits by design and will raise incidents while transmitting.</p>
      </section>

      {log.length > 0 && (
        <section className="panel">
          <h2>Last transmission</h2>
          <ul className="task-list">
            {log.slice(0, 8).map((l) => (
              <li key={l.id} className="task-row">
                <div className="task-main">
                  <span className="cell-strong cell-mono">{l.id.slice(0, 8)}</span>
                  <span className="task-meta">{l.time}{l.error ? ` — ${l.error}` : ''}</span>
                </div>
                <div className="task-badges"><StatusBadge tone={l.ok ? 'ok' : 'bad'}>{l.ok ? 'SENT' : 'FAILED'}</StatusBadge></div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
