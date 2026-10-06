import { useState, useEffect } from 'react';
import { MACHINE_STATUSES } from '../config/machines';

export default function MachinePanel({ machine, sensorValues, baseline, abnormal, onApply, onReset }) {
  const base = baseline || { temperature: 60, vibration: 2, current: 8, rpm: 1400 };
  const abn = abnormal || {
    temperature: base.temperature + 25,
    vibration: base.vibration * 3,
    current: base.current * 1.5,
    rpm: Math.round(base.rpm * 0.8),
  };

  const [temp, setTemp] = useState(sensorValues.temperature ?? base.temperature);
  const [vib, setVib] = useState(sensorValues.vibration ?? base.vibration);
  const [curr, setCurr] = useState(sensorValues.current ?? base.current);
  const [rpm, setRpm] = useState(sensorValues.rpm ?? base.rpm);
  const [status, setStatus] = useState(sensorValues.machine_status ?? 'RUNNING');

  const svTemp = sensorValues.temperature;
  const svVib = sensorValues.vibration;
  const svCurr = sensorValues.current;
  const svRpm = sensorValues.rpm;
  const svStatus = sensorValues.machine_status;

  // Sync when the selection changes or when the selected machine's
  // applied/baseline values change externally. Primitive deps avoid
  // re-syncing on every render; typing is safe because sensorValues
  // only changes on Apply/Reset, which carries the same values.
  useEffect(() => {
    setTemp(svTemp ?? base.temperature);
    setVib(svVib ?? base.vibration);
    setCurr(svCurr ?? base.current);
    setRpm(svRpm ?? base.rpm);
    setStatus(svStatus ?? 'RUNNING');
  }, [machine.id, svTemp, svVib, svCurr, svRpm, svStatus,
      base.temperature, base.vibration, base.current, base.rpm]);

  const handleApply = () => {
    onApply({
      temperature: parseFloat(temp),
      vibration: parseFloat(vib),
      current: parseFloat(curr),
      rpm: parseInt(rpm),
      machine_status: status,
    });
  };

  const handleReset = () => {
    // Clear this machine's pinned override only; live baseline + noise
    // resumes. Other machines are unaffected.
    onReset();
  };

  // Demo presets: fill the inputs AND pin them immediately so the next
  // 10s transmission carries the preset values for this machine only.
  const handleSetAbnormal = () => {
    const values = {
      temperature: abn.temperature,
      vibration: abn.vibration,
      current: abn.current,
      rpm: abn.rpm,
      machine_status: status,
    };
    setTemp(values.temperature);
    setVib(values.vibration);
    setCurr(values.current);
    setRpm(values.rpm);
    onApply(values);
  };

  const handleSetNormal = () => {
    const values = {
      temperature: base.temperature,
      vibration: base.vibration,
      current: base.current,
      rpm: base.rpm,
      machine_status: 'RUNNING',
    };
    setTemp(values.temperature);
    setVib(values.vibration);
    setCurr(values.current);
    setRpm(values.rpm);
    setStatus('RUNNING');
    onApply(values);
  };

  return (
    <div className="machine-panel">
      <div className="panel-header">
        <h2>{machine.name}</h2>
        <div className="panel-sub-header">
          <span className="panel-company-badge">🏢 {machine.company_name || 'CNC / Mechanical'}</span>
          <span className="panel-location">{machine.location}</span>
        </div>
      </div>

      <div className="panel-info">
        <div className="info-row">
          <span className="info-label">Company / Factory:</span>
          <span className="info-company-val">{machine.company_name || 'CNC / Mechanical'}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Type:</span>
          <span>{machine.machine_type}</span>
        </div>
        <div className="info-row">
          <span className="info-label">System Status:</span>
          <span>{machine.status}</span>
        </div>
      </div>

      <h3 className="section-title">Sensor Control Panel</h3>

      <div className="control-group">
        <label>Temperature (°C)</label>
        <div className="control-row">
          <input
            type="number"
            step="0.1"
            value={temp}
            onChange={e => setTemp(e.target.value)}
            className="control-input"
          />
          <input
            type="range"
            min="20"
            max="150"
            step="0.5"
            value={temp}
            onChange={e => setTemp(e.target.value)}
            className="control-slider"
          />
        </div>
        <div className="control-range">20 — 150 °C (baseline: {base.temperature})</div>
      </div>

      <div className="control-group">
        <label>Vibration (mm/s)</label>
        <div className="control-row">
          <input
            type="number"
            step="0.1"
            value={vib}
            onChange={e => setVib(e.target.value)}
            className="control-input"
          />
          <input
            type="range"
            min="0"
            max="15"
            step="0.1"
            value={vib}
            onChange={e => setVib(e.target.value)}
            className="control-slider"
          />
        </div>
        <div className="control-range">0 — 15 mm/s (baseline: {base.vibration})</div>
      </div>

      <div className="control-group">
        <label>Current (A)</label>
        <div className="control-row">
          <input
            type="number"
            step="0.1"
            value={curr}
            onChange={e => setCurr(e.target.value)}
            className="control-input"
          />
          <input
            type="range"
            min="0"
            max="30"
            step="0.1"
            value={curr}
            onChange={e => setCurr(e.target.value)}
            className="control-slider"
          />
        </div>
        <div className="control-range">0 — 30 A (baseline: {base.current})</div>
      </div>

      <div className="control-group">
        <label>RPM</label>
        <div className="control-row">
          <input
            type="number"
            step="10"
            value={rpm}
            onChange={e => setRpm(e.target.value)}
            className="control-input"
          />
          <input
            type="range"
            min="0"
            max="5000"
            step="10"
            value={rpm}
            onChange={e => setRpm(e.target.value)}
            className="control-slider"
          />
        </div>
        <div className="control-range">0 — 5000 RPM (baseline: {base.rpm})</div>
      </div>

      <div className="control-group">
        <label>Machine Status</label>
        <select value={status} onChange={e => setStatus(e.target.value)} className="control-select">
          {MACHINE_STATUSES.map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      <div className="panel-actions">
        <button className="btn btn-primary" onClick={handleApply}>
          ✅ Apply Changes
        </button>
        <button className="btn btn-secondary" onClick={handleReset}>
          ↩ Reset to Baseline
        </button>
      </div>

      <div className="panel-actions">
        <button className="btn btn-warn" onClick={handleSetAbnormal}>
          ⚠ Set Abnormal
        </button>
        <button className="btn btn-ok" onClick={handleSetNormal}>
          ✓ Set Normal
        </button>
      </div>
    </div>
  );
}
