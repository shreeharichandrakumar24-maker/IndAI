import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import StatusBadge from '../StatusBadge';
import EmployeeCode from '../EmployeeCode';

// Deterministic assignment drawer (rule-based): ranked employees/machines
// with reasons and numbers for one unassigned task, then Create proposal
// (POST /ai/proposals). Approval happens in the pending proposals list.
// Labelled rule-based; works with no LLM key and no voice.
export default function SuggestDrawer({ task, onClose, onProposed }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [empId, setEmpId] = useState('');
  const [machId, setMachId] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const res = await api.allocationCandidates(task.id);
        if (!cancelled) {
          setData(res);
          const emps = res.employees || [];
          const machs = res.machines || [];
          if (emps.length > 0) setEmpId(emps[0].id);
          const typeFit = machs.find((m) => m.eligible);
          if (typeFit) setMachId(typeFit.id);
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load candidates');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (task) load();
    return () => { cancelled = true; };
  }, [task]);

  if (!task) return null;

  const createProposal = async () => {
    if (!empId) {
      setError('Pick a worker first (or leave unassigned).');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const res = await api.createProposal({
        action_type: 'REASSIGN_TASK',
        params: { task_id: task.id, employee_id: empId, ...(machId ? { machine_id: machId } : {}) },
        reason: `Rule-based suggestion for ${task.name}`,
      });
      setResult(res);
      if (onProposed) onProposed(res);
    } catch (err) {
      setError(err.message || 'Proposal failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" role="dialog" aria-modal="true" aria-label={`Suggest assignment for ${task.name}`} onClick={(e) => e.stopPropagation()}>
        <div className="details-head">
          <h2>Suggest assignment <span className="muted">— {task.name}</span></h2>
          <button type="button" className="btn-small" onClick={onClose}>Close</button>
        </div>
        <p className="muted">
          <StatusBadge tone="warn">rule-based</StatusBadge> Ranked by skill match, availability, workload and machine health. Nothing is assigned until you approve the proposal.
        </p>
        {loading ? <p className="muted">Loading candidates…</p>
          : error && !data ? <p className="form-errors" role="alert">{error}</p>
          : (
            <>
              <h3 className="section-title">Workers ({(data.employees || []).length} eligible)</h3>
              {(data.employees || []).length === 0 ? <p className="muted">No eligible worker found.</p> : (
                <table className="data-table">
                  <thead><tr><th></th><th>Name</th><th>Open tasks</th><th>Shift fit</th><th>Certifications</th></tr></thead>
                  <tbody>
                    {data.employees.map((e) => (
                      <tr key={e.id} style={empId === e.id ? { background: 'var(--accent-dim)' } : undefined}>
                        <td><input type="radio" name="suggest-emp" checked={empId === e.id} onChange={() => setEmpId(e.id)} aria-label={`Pick ${e.name}`} /></td>
                        <td className="cell-strong">{e.name} <EmployeeCode employeeId={e.id} /></td>
                        <td className="cell-mono">{e.open_tasks}</td>
                        <td className="muted">{e.shift_fit || '—'}</td>
                        <td className="muted">{Array.isArray(e.certifications?.items) ? e.certifications.items.join(', ') : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <h3 className="section-title">Machines</h3>
              <select value={machId} onChange={(e) => setMachId(e.target.value)} style={{ width: '100%' }}>
                <option value="">— keep current —</option>
                {(data.machines || []).filter((m) => m.eligible).map((m) => (
                  <option key={m.id} value={m.id}>{m.name} ({m.health_status || '?'})</option>
                ))}
              </select>
              <p className="muted" style={{ marginTop: 8 }}>
                {(data.machines || []).filter((m) => !m.eligible).length} machine(s) excluded: not operational, open incident, or busy.
              </p>
              {error && <p className="form-errors" role="alert">{error}</p>}
              {result ? (
                <div className="panel" role="status" style={{ marginTop: 8 }}>
                  <p className="muted">Proposal {String(result.id).slice(0, 8)} is PENDING. Approve it in the pending proposals list (voice panel or AI Assistant page).</p>
                </div>
              ) : (
                <div style={{ marginTop: 12 }}>
                  <button type="button" className="btn-primary" disabled={busy || !empId} onClick={createProposal}>
                    {busy ? 'Creating…' : 'Create proposal'}
                  </button>
                </div>
              )}
            </>
          )}
      </div>
    </div>
  );
}
