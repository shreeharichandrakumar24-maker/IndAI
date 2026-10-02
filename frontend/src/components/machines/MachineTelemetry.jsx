import StatusBadge from '../StatusBadge';
import { toneForMachineStatus } from './machineTone';

// Recent telemetry readings for one machine. Uses only the exact
// TelemetryResponse fields: temperature, vibration, current, rpm,
// machine_status, timestamp. Plain table — no chart library.
function fmtNum(value, digits = 1) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isNaN(n) ? '—' : n.toFixed(digits);
}

function fmtTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

export default function MachineTelemetry({ telemetry, loading, error, onRetry }) {
  if (loading) return <p className="muted">Loading telemetry…</p>;
  if (error) {
    return (
      <p className="muted" role="alert">
        Telemetry unavailable: {error}{' '}
        <button type="button" className="btn-small" onClick={onRetry}>
          Retry
        </button>
      </p>
    );
  }
  if (!telemetry || telemetry.length === 0) {
    return <p className="muted">No telemetry recorded for this machine yet.</p>;
  }

  const latest = telemetry[0];

  return (
    <div>
      <div className="details-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <div>
          <span className="detail-label">Latest reading</span>
          <span className="detail-value cell-mono">{fmtTime(latest.timestamp)}</span>
        </div>
        <div>
          <span className="detail-label">Temperature</span>
          <span className="detail-value">{fmtNum(latest.temperature)} °C</span>
        </div>
        <div>
          <span className="detail-label">Vibration</span>
          <span className="detail-value">{fmtNum(latest.vibration, 2)} mm/s</span>
        </div>
        <div>
          <span className="detail-label">Current</span>
          <span className="detail-value">{fmtNum(latest.current, 2)} A</span>
        </div>
        <div>
          <span className="detail-label">RPM</span>
          <span className="detail-value">{fmtNum(latest.rpm, 0)}</span>
        </div>
        <div>
          <span className="detail-label">Reported status</span>
          <span className="detail-value">
            <StatusBadge tone={toneForMachineStatus(latest.machine_status)}>
              {latest.machine_status || '—'}
            </StatusBadge>
          </span>
        </div>
      </div>

      <h4 className="section-title">Recent readings ({telemetry.length})</h4>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Temp °C</th>
              <th>Vib mm/s</th>
              <th>Current A</th>
              <th>RPM</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {telemetry.map((t) => (
              <tr key={t.id}>
                <td className="cell-mono">{fmtTime(t.timestamp)}</td>
                <td>{fmtNum(t.temperature)}</td>
                <td>{fmtNum(t.vibration, 2)}</td>
                <td>{fmtNum(t.current, 2)}</td>
                <td>{fmtNum(t.rpm, 0)}</td>
                <td>
                  <StatusBadge tone={toneForMachineStatus(t.machine_status)}>
                    {t.machine_status || '—'}
                  </StatusBadge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
