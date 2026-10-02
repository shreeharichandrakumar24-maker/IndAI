import { useCallback, useEffect, useState } from 'react';
import { api } from '../../services/api';
import StatusBadge from '../StatusBadge';
import MaintenanceForm from './MaintenanceForm';
import IncidentAnalysis from './IncidentAnalysis';
import SimilarMemory from '../SimilarMemory';
import {
  formatDateTime,
  isActiveIncident,
  issuePrefix,
  linkedMaintenance,
  machineCode,
  stripIssuePrefix,
  toneForIncidentStatus,
  toneForMaintenanceStatus,
  toneForSeverity,
} from './incidentWorkflow';

function fmtReading(value, digits = 1) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isNaN(n) ? '—' : n.toFixed(digits);
}

// Incident workflow modal: incident + machine + live health + linked
// maintenance (prefix convention ONLY) + gated resolve. Completing
// maintenance re-checks health but never auto-resolves the incident.
export default function IncidentDetails({ incident, machine, onClose, onChanged }) {
  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState('');
  const [latest, setLatest] = useState(null);
  const [records, setRecords] = useState([]);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [recordsError, setRecordsError] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [completeTarget, setCompleteTarget] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [actionError, setActionError] = useState('');
  const [actionBusy, setActionBusy] = useState('');
  const [healthNote, setHealthNote] = useState('');

  const loadHealth = useCallback(async () => {
    if (!incident.machine_id) {
      setHealthLoading(false);
      return;
    }
    setHealthLoading(true);
    setHealthError('');
    try {
      const [h, t] = await Promise.all([
        api.machineHealth(incident.machine_id),
        api.latestTelemetry(incident.machine_id).catch(() => null),
      ]);
      setHealth(h);
      setLatest(t);
    } catch (err) {
      setHealthError(err.message || 'Failed to load machine health');
    } finally {
      setHealthLoading(false);
    }
  }, [incident.machine_id]);

  const loadRecords = useCallback(async () => {
    if (!incident.machine_id) {
      setRecordsLoading(false);
      return;
    }
    setRecordsLoading(true);
    setRecordsError('');
    try {
      const data = await api.maintenanceByMachine(incident.machine_id);
      setRecords(linkedMaintenance(Array.isArray(data) ? data : [], incident.id));
    } catch (err) {
      setRecordsError(err.message || 'Failed to load maintenance records');
    } finally {
      setRecordsLoading(false);
    }
  }, [incident.machine_id, incident.id]);

  useEffect(() => {
    loadHealth();
    loadRecords();
  }, [loadHealth, loadRecords]);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadHealth(), loadRecords()]);
    if (onChanged) onChanged();
  }, [loadHealth, loadRecords, onChanged]);

  const openCreate = () => {
    setEditing(null);
    setCompleteTarget(null);
    setFormError('');
    setFormOpen(true);
  };

  const openEdit = (rec) => {
    setEditing(rec);
    setCompleteTarget(null);
    setFormError('');
    setFormOpen(true);
  };

  const openComplete = (rec) => {
    setEditing(rec);
    setCompleteTarget(rec);
    setFormError('');
    setFormOpen(true);
  };

  const handleFormSubmit = async (fields) => {
    setSaving(true);
    setFormError('');
    setActionError('');
    try {
      if (editing) {
        const payload = { status: fields.status };
        if (fields.description !== undefined) payload.description = fields.description;
        if (fields.technician !== undefined) payload.technician = fields.technician;
        if (fields.maintenance_date !== undefined) payload.maintenance_date = fields.maintenance_date;
        if (fields.resolution !== null) payload.resolution = fields.resolution;
        else if (fields.resolution === null) payload.resolution = null;
        // issue suffix is part of the link convention — keep prefix intact.
        await api.updateMaintenance(editing.id, {
          ...payload,
          issue: issuePrefix(incident.id) + fields.issueSuffix,
        });
      } else {
        await api.createMaintenance({
          machine_id: incident.machine_id,
          issue: issuePrefix(incident.id) + fields.issueSuffix,
          description: fields.description,
          technician: fields.technician,
          maintenance_date: fields.maintenance_date,
          resolution: fields.resolution,
          status: fields.status,
        });
      }
      const wasComplete = (editing && completeTarget) || (!editing && fields.status === 'COMPLETED');
      setFormOpen(false);
      setEditing(null);
      setCompleteTarget(null);
      await refreshAll();
      if (wasComplete) {
        // Immediately re-check health and display the actual result.
        try {
          const h = await api.machineHealth(incident.machine_id);
          setHealth(h);
          setHealthNote(
            h.normal === true
              ? 'Maintenance completed. Machine telemetry is currently NORMAL — the incident can now be resolved.'
              : 'Maintenance completed, but the machine is still ABNORMAL. It must return to normal (simulator “Set Normal”) before the incident can be resolved.',
          );
        } catch (err) {
          setHealthNote(`Maintenance completed, but health re-check failed: ${err.message}`);
        }
      }
    } catch (err) {
      setFormError(err.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleStatusAdvance = async (status) => {
    setActionBusy(status);
    setActionError('');
    try {
      await api.updateIncident(incident.id, { status });
      // F10: resolutions become organizational memory (best effort, never blocks).
      if (status === 'RESOLVED') {
        try {
          await api.memoryLog({
            title: `Incident resolved: ${incident.incident_type} (${incident.severity || 'MEDIUM'})`,
            event_type: 'INCIDENT_RESOLVED',
            description: incident.description || '',
            machine_id: incident.machine_id || null,
            order_id: incident.order_id || null,
            task_id: incident.task_id || null,
            resolution_action: `Maintenance completed: ${(records.find((r) => (r.status || '').toUpperCase() === 'COMPLETED')?.resolution || '').slice(0, 500)}`,
            metadata_: { incident_id: incident.id },
          });
        } catch { /* memory is record-only; resolve already succeeded */ }
      }
      await refreshAll();
    } catch (err) {
      setActionError(err.message || 'Update failed');
    } finally {
      setActionBusy('');
    }
  };

  const active = isActiveIncident(incident);
  const completedRecord = records.find((r) => (r.status || '').toUpperCase() === 'COMPLETED');
  const machineNormal = health?.normal === true;
  const canResolve = active && !!completedRecord && machineNormal;

  const resolveHint = !active
    ? 'This incident is already resolved.'
    : !completedRecord
      ? 'Resolution requires a COMPLETED maintenance record linked to this incident.'
      : !machineNormal
        ? 'Resolution requires normal machine telemetry. The machine is still abnormal — see breached conditions below.'
        : 'All conditions satisfied: maintenance completed and telemetry normal.';

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        role="dialog"
        aria-modal="true"
        aria-label={`Incident ${incident.incident_type} details`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="details-head">
          <h2>
            {incident.incident_type} <span className="muted">— Incident</span>
          </h2>
          <button type="button" className="btn-small" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="details-grid">
          <div>
            <span className="detail-label">Severity</span>
            <span className="detail-value">
              <StatusBadge tone={toneForSeverity(incident.severity)}>{incident.severity || '—'}</StatusBadge>
            </span>
          </div>
          <div>
            <span className="detail-label">Status</span>
            <span className="detail-value">
              <StatusBadge tone={toneForIncidentStatus(incident.status)}>{incident.status || 'OPEN'}</StatusBadge>
            </span>
          </div>
          <div>
            <span className="detail-label">Machine</span>
            <span className="detail-value">
              {machine ? `${machineCode(machine.name)} · ${machine.name}` : 'Unlinked'}
            </span>
          </div>
          <div>
            <span className="detail-label">Created</span>
            <span className="detail-value cell-mono">{formatDateTime(incident.created_at)}</span>
          </div>
        </div>
        {incident.description && <p className="muted" style={{ marginTop: 8 }}>{incident.description}</p>}

        <h3 className="section-title">Machine health</h3>
        {healthLoading ? (
          <p className="muted">Checking machine health…</p>
        ) : healthError ? (
          <p className="muted" role="alert">
            {healthError}{' '}
            <button type="button" className="btn-small" onClick={loadHealth}>
              Retry
            </button>
          </p>
        ) : !incident.machine_id ? (
          <p className="muted">No machine linked to this incident.</p>
        ) : health && health.has_telemetry === false ? (
          <p className="muted">No telemetry recorded for this machine yet.</p>
        ) : (
          <>
            <p className="muted">
              Current state:{' '}
              <StatusBadge tone={machineNormal ? 'ok' : 'bad'}>
                {machineNormal ? 'NORMAL' : 'ABNORMAL'}
              </StatusBadge>{' '}
              <span className="cell-mono">as of {formatDateTime(health?.latest_timestamp)}</span>
              {latest && (
                <span>
                  {' '}· {fmtReading(latest.temperature)} °C · {fmtReading(latest.vibration, 2)} vib ·{' '}
                  {fmtReading(latest.current, 2)} A · {fmtReading(latest.rpm, 0)} rpm · {latest.machine_status || '—'}
                </span>
              )}
            </p>
            {!machineNormal && health?.breaches?.length > 0 && (
              <ul className="form-errors" role="alert" style={{ marginTop: 8 }}>
                {health.breaches.map((b) => (
                  <li key={b.field}>
                    {b.field} = {String(b.observed)} (expected {b.expected})
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        {healthNote && (
          <p className="muted" role="status" style={{ marginTop: 8 }}>
            {healthNote}
          </p>
        )}
        <div style={{ marginTop: 8 }}>
          <button type="button" className="btn-secondary" onClick={loadHealth} disabled={healthLoading}>
            {healthLoading ? 'Checking…' : '↻ Check Machine / Refresh Health'}
          </button>
        </div>

        <h3 className="section-title">Linked maintenance ({records.length})</h3>
        {recordsLoading ? (
          <p className="muted">Loading maintenance…</p>
        ) : recordsError ? (
          <p className="muted" role="alert">
            {recordsError}{' '}
            <button type="button" className="btn-small" onClick={loadRecords}>
              Retry
            </button>
          </p>
        ) : records.length === 0 ? (
          <p className="muted">
            No maintenance linked to this incident yet. Records link by the issue prefix “Incident {String(incident.id).slice(0, 8)}…” —
            same-machine records without that prefix are not shown here.
          </p>
        ) : (
          <ul className="task-list">
            {records.map((r) => (
              <li key={r.id} className="task-row">
                <div className="task-main">
                  <span className="cell-strong">{stripIssuePrefix(r.issue, incident.id)}</span>
                  <span className="task-meta">
                    Technician (free text): {r.technician || 'unassigned'}
                    {r.resolution ? ` · Resolution: ${r.resolution}` : ''}
                    {r.maintenance_date ? ` · ${formatDateTime(r.maintenance_date)}` : ''}
                  </span>
                </div>
                <div className="task-badges">
                  <StatusBadge tone={toneForMaintenanceStatus(r.status)}>{r.status || 'PENDING'}</StatusBadge>
                </div>
                <div className="cell-actions">
                  <button type="button" className="btn-small" onClick={() => openEdit(r)}>
                    Edit
                  </button>
                  {(r.status || '').toUpperCase() !== 'COMPLETED' && (
                    <button type="button" className="btn-small" onClick={() => openComplete(r)}>
                      Complete
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        {active && incident.machine_id && (
          <div style={{ marginTop: 12 }}>
            <button type="button" className="btn-primary" onClick={openCreate}>
              + Create Maintenance
            </button>
          </div>
        )}

        <IncidentAnalysis incident={incident} onChanged={refreshAll} />

        <SimilarMemory incidentId={incident.id} machineId={incident.machine_id} orderId={incident.order_id} />

        <h3 className="section-title">Resolution</h3>
        <p className="muted">{resolveHint}</p>
        {actionError && (
          <p className="form-errors" role="alert" style={{ marginTop: 8 }}>
            {actionError}
          </p>
        )}
        <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
          {active && (incident.status || 'OPEN').toUpperCase() === 'OPEN' && (
            <button
              type="button"
              className="btn-secondary"
              disabled={!!actionBusy}
              onClick={() => handleStatusAdvance('IN_PROGRESS')}
            >
              {actionBusy === 'IN_PROGRESS' ? 'Updating…' : 'Mark In Progress'}
            </button>
          )}
          <button
            type="button"
            className="btn-primary"
            disabled={!canResolve || !!actionBusy}
            onClick={() => handleStatusAdvance('RESOLVED')}
            title={!canResolve ? resolveHint : 'Resolve this incident'}
          >
            {actionBusy === 'RESOLVED' ? 'Resolving…' : 'Resolve Incident'}
          </button>
        </div>
      </div>

      {formOpen && (
        <MaintenanceForm
          key={`${editing ? editing.id : 'new'}-${completeTarget ? 'complete' : 'edit'}`}
          incident={incident}
          machineName={machine ? machine.name : 'Unknown machine'}
          record={editing}
          defaultStatus={completeTarget ? 'COMPLETED' : 'PENDING'}
          saving={saving}
          apiError={formError}
          onSubmit={handleFormSubmit}
          onClose={() => {
            if (!saving) {
              setFormOpen(false);
              setEditing(null);
              setCompleteTarget(null);
            }
          }}
        />
      )}
    </div>
  );
}
