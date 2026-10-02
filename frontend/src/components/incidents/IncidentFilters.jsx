export default function IncidentFilters({
  search,
  onSearch,
  status,
  onStatus,
  statuses,
  severity,
  onSeverity,
  severities,
  machineId,
  onMachineId,
  machines,
}) {
  return (
    <div className="filter-bar">
      <input
        type="search"
        className="filter-search"
        placeholder="Search by type or description…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        aria-label="Search incidents"
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
        value={severity}
        onChange={(e) => onSeverity(e.target.value)}
        aria-label="Filter by severity"
      >
        <option value="">All severities</option>
        {severities.map((s) => (
          <option key={s} value={s}>
            {s}
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
