import StatusBadge from '../StatusBadge';
import {
  formatDateTime,
  formatReading,
  freshnessOf,
  machineCode,
  toneForTelemetryStatus,
} from './telemetryUtils';

// One card per machine: identity + latest sensor values + data freshness.
// Machines without telemetry render an explicit NO DATA state, never zeros.
export default function MachineTelemetryGrid({ machines, latestById, loading, selectedId, onSelect }) {
  if (loading) return <p className="muted">Loading machine telemetry…</p>;
  if (machines.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-title">No machines registered yet.</p>
        <p className="muted">The IoT simulator seeds the M-001…M-008 fleet on first run.</p>
      </div>
    );
  }

  return (
    <div className="panel-grid">
      {machines.map((m) => {
        const latest = latestById[m.id] || null;
        const fresh = freshnessOf(latest?.timestamp);
        const selected = selectedId === m.id;
        return (
          <section className="panel" key={m.id} aria-label={`Telemetry for ${m.name}`}>
            <div className="details-head">
              <h2>
                {machineCode(m.name)} <span className="muted">· {m.name}</span>
              </h2>
              <StatusBadge tone={fresh.tone}>{fresh.label}</StatusBadge>
            </div>
            {!latest ? (
              <p className="muted">No telemetry received for this machine yet.</p>
            ) : (
              <>
                <div className="details-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
                  <div>
                    <span className="detail-label">Temperature</span>
                    <span className="detail-value">{formatReading(latest.temperature)} °C</span>
                  </div>
                  <div>
                    <span className="detail-label">Vibration</span>
                    <span className="detail-value">{formatReading(latest.vibration, 2)}</span>
                  </div>
                  <div>
                    <span className="detail-label">Current</span>
                    <span className="detail-value">{formatReading(latest.current, 2)} A</span>
                  </div>
                  <div>
                    <span className="detail-label">RPM</span>
                    <span className="detail-value">{formatReading(latest.rpm, 0)} rpm</span>
                  </div>
                  <div>
                    <span className="detail-label">Reported status</span>
                    <span className="detail-value">
                      <StatusBadge tone={toneForTelemetryStatus(latest.machine_status)}>
                        {latest.machine_status || '—'}
                      </StatusBadge>
                    </span>
                  </div>
                  <div>
                    <span className="detail-label">Reading at</span>
                    <span className="detail-value cell-mono">{formatDateTime(latest.timestamp)}</span>
                  </div>
                </div>
              </>
            )}
            <div style={{ marginTop: 12 }}>
              <button
                type="button"
                className={selected ? 'btn-primary' : 'btn-secondary'}
                onClick={() => onSelect(selected ? null : m)}
              >
                {selected ? 'Selected — hide history' : 'View history'}
              </button>
            </div>
          </section>
        );
      })}
    </div>
  );
}
