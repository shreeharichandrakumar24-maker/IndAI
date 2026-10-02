export default function OrderFilters({ search, onSearch, status, onStatus, statuses }) {
  return (
    <div className="filter-bar">
      <input
        type="search"
        className="filter-search"
        placeholder="Search by order no., customer, or product…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        aria-label="Search orders"
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
    </div>
  );
}
