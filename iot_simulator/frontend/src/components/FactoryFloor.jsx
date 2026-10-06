import { MACHINE_STATUSES, machineCode } from '../config/machines';
import { HEALTH_COLORS } from '../utils/health';

const STATUS_COLORS = {
  RUNNING: '#22c55e',
  IDLE: '#eab308',
  MAINTENANCE: '#f97316',
  STOPPED: '#ef4444',
};

export default function FactoryFloor({ machines, selectedId, onSelect, effectiveById, healthById }) {
  return (
    <div className="factory-floor">
      <div className="floor-title">FACTORY FLOOR — {machines.length} MACHINES</div>
      {machines.length === 0 ? (
        <div className="floor-empty">Waiting for machines…</div>
      ) : (
        <div className="floor-grid">
          {machines.map((machine) => {
            const effective = effectiveById[machine.id] || {};
            const status = effective.machine_status || 'RUNNING';
            const health = healthById[machine.id] || 'GOOD';
            const isSelected = machine.id === selectedId;
            const color = STATUS_COLORS[status] || '#6b7280';

            return (
              <div
                key={machine.id}
                className={`machine-cell ${isSelected ? 'selected' : ''} health-${health.toLowerCase()}`}
                onClick={() => onSelect(machine.id)}
                style={{ borderColor: isSelected ? '#3b82f6' : undefined }}
                title={`${machine.name} [${machine.company_name || 'Factory'}] — ${status} / ${health}`}
              >
                <div className="machine-company-tag" title={machine.company_name || 'Factory'}>
                  {machine.company_name || 'Factory'}
                </div>
                <div className="machine-code">{machineCode(machine.name) || machine.name.split(' ')[0]}</div>
                <div className="machine-indicator" style={{ backgroundColor: HEALTH_COLORS[health] || color }} />
                <div className="machine-type">{machine.machine_type}</div>
                <div className="machine-status-badge" style={{ color }}>
                  {status}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="floor-legend">
        {MACHINE_STATUSES.map(s => (
          <span key={s} className="legend-item">
            <span className="legend-dot" style={{ backgroundColor: STATUS_COLORS[s] }} />
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}
