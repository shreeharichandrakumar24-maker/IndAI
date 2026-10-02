import StatusBadge from '../StatusBadge';
import { formatDateTime, machineCode, toneForIncidentStatus, toneForSeverity } from './incidentWorkflow';

export default function IncidentTable({ incidents, loading, machineById, onOpen }) {
  if (loading) return <p className="muted">Loading incidents…</p>;
  if (incidents.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-title">No incidents registered.</p>
        <p className="muted">Run “Check All Machines” to detect abnormal telemetry, or wait for the next detection.</p>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Severity</th>
            <th>Type</th>
            <th>Machine</th>
            <th>Status</th>
            <th>Description</th>
            <th>Created</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {incidents.map((i) => {
            const machine = machineById[i.machine_id];
            const active = (i.status || 'OPEN').toUpperCase() !== 'RESOLVED';
            return (
              <tr key={i.id} style={active ? undefined : { opacity: 0.75 }}>
                <td>
                  <StatusBadge tone={toneForSeverity(i.severity)}>{i.severity || '—'}</StatusBadge>
                </td>
                <td className="cell-strong">{i.incident_type}</td>
                <td>{machine ? `${machineCode(machine.name)} · ${machine.name}` : '—'}</td>
                <td>
                  <StatusBadge tone={toneForIncidentStatus(i.status)}>{i.status || 'OPEN'}</StatusBadge>
                </td>
                <td className="cell-truncate" title={i.description || ''}>
                  {i.description || '—'}
                </td>
                <td className="cell-mono">{formatDateTime(i.created_at)}</td>
                <td className="cell-actions">
                  <button type="button" className="btn-small" onClick={() => onOpen(i)}>
                    Open
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
