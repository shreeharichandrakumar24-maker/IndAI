import StatusBadge from '../StatusBadge';
import SensorValueCard from './SensorValueCard';
import {
  formatDateTime,
  formatReading,
  machineCode,
  toneForTelemetryStatus,
} from './telemetryUtils';

// Selected-machine detail: latest reading as sensor cards plus a readable
// recent-history table (newest first). No charts, no derived scores.
export default function TelemetryDetails({ machine, history, historyLoading, historyError, onRetry, onClose }) {
  if (!machine) return null;
  const latest = history.length > 0 ? history[0] : null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        role="dialog"
        aria-modal="true"
        aria-label={`Telemetry history for ${machine.name}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="details-head">
          <h2>
            {machineCode(machine.name)} <span className="muted">· {machine.name} — telemetry history</span>
          </h2>
          <button type="button" className="btn-small" onClick={onClose}>
            Close
          </button>
        </div>

        <h3 className="section-title">Latest reading</h3>
        {historyLoading ? (
          <p className="muted">Loading telemetry…</p>
        ) : historyError ? (
          <p className="muted" role="alert">
            Telemetry unavailable: {historyError}{' '}
            <button type="button" className="btn-small" onClick={onRetry}>
              Retry
            </button>
          </p>
        ) : !latest ? (
          <p className="muted">No telemetry recorded for this machine yet.</p>
        ) : (
          <section
            className="stat-grid"
            aria-label="Latest sensor values"
            style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}
          >
            <SensorValueCard label="Temperature" value={formatReading(latest.temperature)} unit="°C" />
            <SensorValueCard label="Vibration" value={formatReading(latest.vibration, 2)} />
            <SensorValueCard label="Current" value={formatReading(latest.current, 2)} unit="A" />
            <SensorValueCard label="RPM" value={formatReading(latest.rpm, 0)} unit="rpm" />
            <div className="stat-card">
              <div className="stat-label">Reported status</div>
              <div className="stat-value" style={{ fontSize: '1.1rem', marginTop: 8 }}>
                <StatusBadge tone={toneForTelemetryStatus(latest.machine_status)}>
                  {latest.machine_status || '—'}
                </StatusBadge>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Reading at</div>
              <div className="stat-value cell-mono" style={{ fontSize: '0.95rem', marginTop: 8 }}>
                {formatDateTime(latest.timestamp)}
              </div>
            </div>
          </section>
        )}

        <h3 className="section-title">Recent history ({history.length})</h3>
        {!historyLoading && !historyError && history.length > 0 && (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Temp °C</th>
                  <th>Vibration</th>
                  <th>Current A</th>
                  <th>RPM</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {history.map((t) => (
                  <tr key={t.id}>
                    <td className="cell-mono">{formatDateTime(t.timestamp)}</td>
                    <td>{formatReading(t.temperature)}</td>
                    <td>{formatReading(t.vibration, 2)}</td>
                    <td>{formatReading(t.current, 2)}</td>
                    <td>{formatReading(t.rpm, 0)}</td>
                    <td>
                      <StatusBadge tone={toneForTelemetryStatus(t.machine_status)}>
                        {t.machine_status || '—'}
                      </StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
