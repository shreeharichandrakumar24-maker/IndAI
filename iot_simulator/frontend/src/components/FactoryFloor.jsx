import { MACHINE_STATUSES, machineCode } from '../config/machines';
import { HEALTH_COLORS } from '../utils/health';

const STATUS_COLORS = {
  RUNNING: '#22c55e',
  IDLE: '#eab308',
  MAINTENANCE: '#f97316',
  STOPPED: '#ef4444',
};

export default function FactoryFloor({ machines, selectedId, onSelect, effectiveById, healthById, effectiveAlerts = {} }) {
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
            const alert = effectiveAlerts[machine.id];

            return (
              <div
                key={machine.id}
                className={`machine-cell ${isSelected ? 'selected' : ''} health-${health.toLowerCase()} ${alert ? 'has-active-alert' : ''}`}
                onClick={() => onSelect(machine.id)}
                style={{ borderColor: isSelected ? '#3b82f6' : (alert ? '#ef4444' : undefined) }}
                title={`${machine.name} [${machine.company_name || 'Factory'}] — ${status} / ${health}${alert ? ' | ALERT: High Temp!' : ''}`}
              >
                <div className="machine-company-tag" title={machine.company_name || 'Factory'}>
                  {machine.company_name || 'Factory'}
                </div>
                <div className="machine-code">{machineCode(machine.name) || machine.name.split(' ')[0]}</div>
                <div className="machine-indicator" style={{ backgroundColor: alert ? '#ef4444' : (HEALTH_COLORS[health] || color) }} />
                <div className="machine-type">{machine.machine_type}</div>
                <div className="machine-status-badge" style={{ color: alert ? '#ef4444' : color }}>
                  {alert ? '⚠ ALERT' : status}
                </div>
                {alert && (
                  <div className="machine-alert-summary">
                    <div className="alert-badge-mini">🌡️ {alert.temperature}°C</div>
                    <div className="service-man-mini" title={`Service Man: ${alert.serviceMan?.name}`}>
                      👨‍🔧 {alert.serviceMan?.name?.split(' ')[0] || 'Service Man'}
                    </div>
                  </div>
                )}
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
