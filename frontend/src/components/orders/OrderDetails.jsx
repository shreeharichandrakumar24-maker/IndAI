import { useCallback, useEffect, useState } from 'react';
import { api } from '../../services/api';
import StatusBadge from '../StatusBadge';
import DeepAnalysis from '../DeepAnalysis';
import { toneForOrderStatus, toneForTaskStatus, formatDateTime } from '../../utils/orders';
import ManualSplitPanel from './ManualSplitPanel';
import SmartSplitPanel from './SmartSplitPanel';

export default function OrderDetails({ order, employees, machines, onClose, onOrderChanged }) {
  const [tab, setTab] = useState('manual');
  const [tasks, setTasks] = useState([]);
  const [tasksLoading, setTasksLoading] = useState(true);
  const [tasksError, setTasksError] = useState('');

  const employeeById = Object.fromEntries(employees.map((e) => [e.id, e]));
  const machineById = Object.fromEntries(machines.map((m) => [m.id, m]));

  const loadTasks = useCallback(async () => {
    setTasksLoading(true);
    setTasksError('');
    try {
      const data = await api.tasksByOrder(order.id);
      setTasks(Array.isArray(data) ? data : []);
    } catch (err) {
      setTasksError(err.message || 'Failed to load tasks');
    } finally {
      setTasksLoading(false);
    }
  }, [order.id]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        role="dialog"
        aria-modal="true"
        aria-label={`Order ${order.order_number} planning`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="details-head">
          <h2>
            {order.order_number} <span className="muted">— Order Planning</span>
          </h2>
          <button type="button" className="btn-small" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="details-grid">
          <div>
            <span className="detail-label">Customer</span>
            <span className="detail-value">{order.customer_name || '—'}</span>
          </div>
          <div>
            <span className="detail-label">Product</span>
            <span className="detail-value">{order.product || '—'}</span>
          </div>
          <div>
            <span className="detail-label">Quantity</span>
            <span className="detail-value">{order.quantity ?? '—'}</span>
          </div>
          <div>
            <span className="detail-label">Progress</span>
            <span className="detail-value">{order.progress ?? '—'}</span>
          </div>
          <div>
            <span className="detail-label">Priority</span>
            <span className="detail-value">{order.priority || '—'}</span>
          </div>
          <div>
            <span className="detail-label">Status</span>
            <span className="detail-value">
              <StatusBadge tone={toneForOrderStatus(order.status)}>{order.status || 'PENDING'}</StatusBadge>
            </span>
          </div>
          <div>
            <span className="detail-label">Deadline</span>
            <span className="detail-value">{formatDateTime(order.deadline)}</span>
          </div>
          <div>
            <span className="detail-label">Order ID</span>
            <span className="detail-value cell-mono">{String(order.id).slice(0, 8)}</span>
          </div>
        </div>

        <h3 className="section-title">Tasks for this order ({tasks.length})</h3>
        {tasksLoading ? (
          <p className="muted">Loading tasks…</p>
        ) : tasksError ? (
          <div className="alert-banner" role="alert">
            {tasksError}{' '}
            <button type="button" className="btn-small" onClick={loadTasks}>
              Retry
            </button>
          </div>
        ) : tasks.length === 0 ? (
          <p className="muted">No tasks created for this order yet.</p>
        ) : (
          <ul className="task-list">
            {tasks.map((t) => (
              <li key={t.id} className="task-row">
                <div className="task-main">
                  <span className="cell-strong">{t.name}</span>
                  <span className="muted">{t.description || 'No description'}</span>
                  <span className="task-meta">
                    {employeeById[t.employee_id] ? `👤 ${employeeById[t.employee_id].name}` : '👤 Unassigned'}
                    {' · '}
                    {machineById[t.machine_id] ? `⚙ ${machineById[t.machine_id].name}` : '⚙ Unassigned'}
                    {t.deadline ? ` · due ${formatDateTime(t.deadline)}` : ''}
                  </span>
                </div>
                <div className="task-badges">
                  <StatusBadge tone={toneForTaskStatus(t.status)}>{t.status || 'PENDING'}</StatusBadge>
                  <StatusBadge tone="neutral">{t.priority || 'NORMAL'}</StatusBadge>
                </div>
              </li>
            ))}
          </ul>
        )}

        <h3 className="section-title">Split Order</h3>
        <div className="split-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'manual'}
            className={`split-tab${tab === 'manual' ? ' active' : ''}`}
            onClick={() => setTab('manual')}
          >
            Manual Split
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'smart'}
            className={`split-tab${tab === 'smart' ? ' active' : ''}`}
            onClick={() => setTab('smart')}
          >
            Smart Split (AI)
          </button>
        </div>

        {tab === 'manual' ? (
          <ManualSplitPanel
            order={order}
            employees={employees}
            machines={machines}
            onTaskCreated={() => {
              loadTasks();
              if (onOrderChanged) onOrderChanged();
            }}
          />
        ) : (
          <SmartSplitPanel
            order={order}
            employees={employees}
            machines={machines}
            onTaskCreated={() => {
              loadTasks();
              if (onOrderChanged) onOrderChanged();
            }}
          />
        )}

        <DeepAnalysis scope={{ order_id: order.id }} />
      </div>
    </div>
  );
}
