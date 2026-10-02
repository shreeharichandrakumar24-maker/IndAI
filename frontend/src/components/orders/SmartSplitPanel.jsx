import { useState } from 'react';
import { api } from '../../services/api';
import { requestSmartSplit } from '../../services/smartSplit';
import StatusBadge from '../StatusBadge';

// Smart Split (AI-assisted): Generate -> editable proposal table ->
// Approve creates tasks via POST /tasks (sequential, per-row report).
// Nothing is created before the approve click. Manual Split untouched.
const EMPTY_ROW = { name: '', description: '', required_skill: '', priority: 'NORMAL', machine_id: '', employee_id: '', suggested_deadline: '' };

export default function SmartSplitPanel({ order, employees, machines, onTaskCreated }) {
  const [proposal, setProposal] = useState(null);
  const [rows, setRows] = useState([]);
  const [removed, setRemoved] = useState([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [report, setReport] = useState(null);

  if (!order) return <p className="muted">Open an order to use Smart Split.</p>;

  const generate = async () => {
    setBusy('generate');
    setError('');
    setReport(null);
    try {
      const res = await requestSmartSplit(order.id);
      setProposal(res);
      setRows((res.proposed_tasks || []).map((t) => ({
        name: t.name || '',
        description: t.description || '',
        required_skill: t.required_skill || '',
        priority: t.priority || 'NORMAL',
        machine_id: t.machine_id || '',
        employee_id: t.employee_id || '',
        suggested_deadline: (t.suggested_deadline || '').slice(0, 16),
        rationale: t.rationale || '',
        candidates: t.candidates || { employees: [], machines: [] },
      })));
      setRemoved([]);
    } catch (err) {
      setError(err.message || 'Smart Split failed');
    } finally {
      setBusy('');
    }
  };

  const setCell = (i, k, v) => setRows((l) => l.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  const removeRow = (i) => {
    setRows((l) => l.filter((_, j) => j !== i));
    setRemoved((l) => l + 1);
  };

  const approve = async () => {
    setBusy('approve');
    setError('');
    const results = [];
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      if (!r.name.trim()) {
        results.push({ row: i + 1, ok: false, error: 'Name required' });
        continue;
      }
      const payload = {
        name: r.name.trim(),
        order_id: order.id,
        priority: r.priority || 'NORMAL',
        status: 'PENDING',
        progress: 0,
      };
      if (r.description.trim()) payload.description = r.description.trim();
      if (r.required_skill.trim()) payload.required_skill = r.required_skill.trim();
      if (r.employee_id) payload.employee_id = r.employee_id;
      if (r.machine_id) payload.machine_id = r.machine_id;
      if (r.suggested_deadline) {
        const d = new Date(r.suggested_deadline);
        if (!Number.isNaN(d.getTime())) payload.deadline = d.toISOString();
      }
      try {
        const created = await api.createTask(payload);
        results.push({ row: i + 1, ok: true, id: created.id, name: r.name.trim() });
      } catch (err) {
        results.push({ row: i + 1, ok: false, error: err.message || 'Create failed' });
      }
    }
    setReport({ results, ok: results.filter((x) => x.ok).length, failed: results.filter((x) => !x.ok).length });
    setBusy('');
    if (onTaskCreated) onTaskCreated();
  };

  const empName = (id) => (employees || []).find((e) => e.id === id)?.name || (id ? id.slice(0, 8) : '—');
  const machName = (id) => {
    const m = (machines || []).find((x) => x.id === id);
    if (!m) return id ? id.slice(0, 8) : '—';
    const code = /^M-\d{3}/.exec(m.name || '');
    return code ? code[0] : m.name;
  };

  return (
    <div className="split-panel">
      <h4>Smart Split (AI) — {order.order_number}</h4>
      {!proposal ? (
        <>
          <p className="muted">Generates an editable task breakdown with suggested workers and machines. Nothing is created until you approve.</p>
          <button type="button" className="btn-primary" disabled={busy === 'generate'} onClick={generate}>
            {busy === 'generate' ? 'Generating…' : '✦ Generate proposal'}
          </button>
        </>
      ) : (
        <>
          <p className="muted" role="status">
            <StatusBadge tone={proposal.source === 'ai' ? 'info' : 'warn'}>
              {proposal.source === 'ai' ? 'AI proposal' : 'Rule-based (AI unavailable)'}
            </StatusBadge>{' '}
            {proposal.summary}
            {removed > 0 && ` · ${removed} row(s) removed by you`}
          </p>
          <table className="data-table">
            <thead><tr><th>#</th><th>Name</th><th>Skill</th><th>Prio</th><th>Machine</th><th>Worker</th><th>Deadline</th><th></th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="cell-mono">{i + 1}</td>
                  <td><input value={r.name} onChange={(e) => setCell(i, 'name', e.target.value)} placeholder="Task name" /></td>
                  <td><input value={r.required_skill} onChange={(e) => setCell(i, 'required_skill', e.target.value)} placeholder="Skill" /></td>
                  <td>
                    <select value={r.priority} onChange={(e) => setCell(i, 'priority', e.target.value)}>
                      {['LOW', 'NORMAL', 'HIGH', 'URGENT'].map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </td>
                  <td>
                    <select value={r.machine_id} onChange={(e) => setCell(i, 'machine_id', e.target.value)} title={r.rationale}>
                      <option value="">— None —</option>
                      {(r.candidates.machines || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                      {r.machine_id && !(r.candidates.machines || []).some((m) => m.id === r.machine_id) && (
                        <option value={r.machine_id}>{machName(r.machine_id)} (outside candidates)</option>
                      )}
                    </select>
                  </td>
                  <td>
                    <select value={r.employee_id} onChange={(e) => setCell(i, 'employee_id', e.target.value)} title={r.rationale}>
                      <option value="">— None —</option>
                      {(r.candidates.employees || []).map((e) => <option key={e.id} value={e.id}>{e.name} ({e.open_tasks} open)</option>)}
                      {r.employee_id && !(r.candidates.employees || []).some((e) => e.id === r.employee_id) && (
                        <option value={r.employee_id}>{empName(r.employee_id)} (outside candidates)</option>
                      )}
                    </select>
                  </td>
                  <td><input type="datetime-local" value={r.suggested_deadline} onChange={(e) => setCell(i, 'suggested_deadline', e.target.value)} /></td>
                  <td><button type="button" className="btn-small" onClick={() => removeRow(i)}>✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.map((r, i) => r.rationale && (
            <p className="muted" key={i}>Row {i + 1}: {r.rationale} Suggested: {machName(r.machine_id)} / {empName(r.employee_id)}.</p>
          ))}
          <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
            <button type="button" className="btn-small" onClick={() => setRows((l) => [...l, { ...EMPTY_ROW, candidates: { employees: [], machines: [] } }])}>+ Add row</button>
            <button type="button" className="btn-primary" disabled={busy === 'approve' || rows.length === 0} onClick={approve}>
              {busy === 'approve' ? 'Creating…' : `Approve and create ${rows.length} task(s)`}
            </button>
            <button type="button" className="btn-secondary" onClick={generate} disabled={busy === 'generate'}>↻ Regenerate</button>
          </div>
        </>
      )}
      {error && <p className="form-errors" role="alert" style={{ marginTop: 8 }}>{error}</p>}
      {report && (
        <div className="panel" role="status" style={{ marginTop: 8 }}>
          <p className="muted">Created {report.ok}, failed {report.failed}.</p>
          <ul className="form-errors">
            {report.results.filter((r) => !r.ok).map((r) => <li key={r.row}>Row {r.row}: {r.error}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
