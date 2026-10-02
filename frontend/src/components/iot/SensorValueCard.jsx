export default function SensorValueCard({ label, value, unit, loading }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ fontSize: '1.3rem' }}>
        {loading ? '—' : value}
        {unit && !loading && value !== '—' && (
          <span className="stat-sub" style={{ marginLeft: 6 }}>
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}
