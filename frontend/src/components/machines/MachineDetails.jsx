import { useCallback, useEffect, useState } from 'react';
import { api } from '../../services/api';
import StatusBadge from '../StatusBadge';
import DeepAnalysis from '../DeepAnalysis';
import { toneForHealth, toneForMachineStatus } from './machineTone';
import MachineTelemetry from './MachineTelemetry';
import SimilarMemory from '../SimilarMemory';

function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

// Details modal for one machine: actual MachineResponse fields plus the
// latest IoT telemetry (GET /api/machines/{id}/telemetry). No AI analysis,
// no alert logic.
export default function MachineDetails({ machine, onClose }) {
  const [telemetry, setTelemetry] = useState([]);
  const [telLoading, setTelLoading] = useState(true);
  const [telError, setTelError] = useState('');

  const loadTelemetry = useCallback(async () => {
    if (!machine) return;
    setTelLoading(true);
    setTelError('');
    try {
      const data = await api.machineTelemetry(machine.id, 20);
      setTelemetry(Array.isArray(data) ? data : []);
    } catch (err) {
      setTelError(err.message || 'Failed to load telemetry');
    } finally {
      setTelLoading(false);
    }
  }, [machine]);

  useEffect(() => {
    loadTelemetry();
  }, [loadTelemetry]);

  if (!machine) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        role="dialog"
        aria-modal="true"
        aria-label={`Machine details for ${machine.name}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="details-head">
          <h2>{machine.name}</h2>
          <button type="button" className="btn-small" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="details-grid">
          <div>
            <span className="detail-label">Machine ID</span>
            <span className="detail-value cell-mono">{String(machine.id).slice(0, 8)}</span>
          </div>
          <div>
            <span className="detail-label">Type</span>
            <span className="detail-value">{machine.machine_type || '—'}</span>
          </div>
          <div>
            <span className="detail-label">Location</span>
            <span className="detail-value">{machine.location || '—'}</span>
          </div>
          <div>
            <span className="detail-label">Status</span>
            <span className="detail-value">
              <StatusBadge tone={toneForMachineStatus(machine.status)}>
                {machine.status || '—'}
              </StatusBadge>
            </span>
          </div>
          <div>
            <span className="detail-label">Health</span>
            <span className="detail-value">
              <StatusBadge tone={toneForHealth(machine.health_status)}>
                {machine.health_status || '—'}
              </StatusBadge>
            </span>
          </div>
          <div>
            <span className="detail-label">Created</span>
            <span className="detail-value cell-mono">{fmtDate(machine.created_at)}</span>
          </div>
          <div>
            <span className="detail-label">Updated</span>
            <span className="detail-value cell-mono">{fmtDate(machine.updated_at)}</span>
          </div>
          <div>
            <span className="detail-label">Full UUID</span>
            <span className="detail-value cell-mono" title={machine.id}>
              {machine.id}
            </span>
          </div>
        </div>

        <h3 className="section-title">Latest IoT telemetry → machine readings</h3>
        <MachineTelemetry
          telemetry={telemetry}
          loading={telLoading}
          error={telError}
          onRetry={loadTelemetry}
        />

        <DeepAnalysis scope={{ machine_id: machine.id }} />

        <SimilarMemory machineId={machine.id} />
      </div>
    </div>
  );
}
