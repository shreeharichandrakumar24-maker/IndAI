export default function TelemetryFilters({ search, onSearch, status, onStatus, statuses }) {
  return (
    <div className="filter-bar">
      <input
        type="search"
        className="filter-search"
        placeholder="Search by machine name, code, or ID…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        aria-label="Search monitored machines"
      />
      <select
        className="filter-select"
        value={status}
        onChange={(e) => onStatus(e.target.value)}
        aria-label="Filter by reported status"
      >
        <option value="">All reported statuses</option>
        {statuses.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
    </div>
  );
}
