import { TASK_STATUSES, TASK_PRIORITIES } from './taskWorkflow';

export default function TaskFilters({
  search, onSearch, status, onStatus, statuses,
  priority, onPriority, assignee, onAssignee, employees,
  machine, onMachine, machines, order, onOrder, orders,
}) {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
      <input
        placeholder="Search name / skill…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        style={{ minWidth: 200 }}
      />
      <select value={status} onChange={(e) => onStatus(e.target.value)}>
        <option value="">All statuses</option>
        {(statuses.length > 0 ? statuses : TASK_STATUSES).map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <select value={priority} onChange={(e) => onPriority(e.target.value)}>
        <option value="">All priorities</option>
        {TASK_PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <select value={assignee} onChange={(e) => onAssignee(e.target.value)}>
        <option value="">All assignees</option>
        {(employees || []).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
      </select>
      <select value={machine} onChange={(e) => onMachine(e.target.value)}>
        <option value="">All machines</option>
        {(machines || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
      </select>
      <select value={order} onChange={(e) => onOrder(e.target.value)}>
        <option value="">All orders</option>
        {(orders || []).map((o) => <option key={o.id} value={o.id}>{o.order_number}</option>)}
      </select>
    </div>
  );
}
