export default function ProductionFilters({
  search,
  onSearch,
  status,
  onStatus,
  statuses,
  orderId,
  onOrderId,
  orders,
  machineId,
  onMachineId,
  machines,
}) {
  return (
    <div className="filter-bar">
      <input
        type="search"
        className="filter-search"
        placeholder="Search by run ID…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        aria-label="Search production runs"
      />
      <select
        className="filter-select"
        value={status}
        onChange={(e) => onStatus(e.target.value)}
        aria-label="Filter by status"
      >
        <option value="">All statuses</option>
        {statuses.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <select
        className="filter-select"
        value={orderId}
        onChange={(e) => onOrderId(e.target.value)}
        aria-label="Filter by order"
      >
        <option value="">All orders</option>
        {orders.map((o) => (
          <option key={o.id} value={o.id}>
            {o.order_number || String(o.id).slice(0, 8)}
          </option>
        ))}
      </select>
      <select
        className="filter-select"
        value={machineId}
        onChange={(e) => onMachineId(e.target.value)}
        aria-label="Filter by machine"
      >
        <option value="">All machines</option>
        {machines.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </select>
    </div>
  );
}
