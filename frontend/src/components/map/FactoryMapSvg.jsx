import { useRef } from 'react';
import { clamp, snap, typeGlyph } from './mapUtils';

const TONE_FILL = { ok: '#22c55e', bad: '#ef4444', stale: '#64748b' };

// Responsive inline SVG floor plan. Zones as labeled rectangles, machines as
// draggable nodes (edit mode only; pointer events, snap-to-grid, clamped,
// touch-capable). Open incidents render a red pulsing ring (SVG animate).
export default function FactoryMapSvg({
  width, height, zones, nodes, selectedCode, dimmed, editMode, onSelect, onMove,
}) {
  const svgRef = useRef(null);

  const toLocal = (clientX, clientY) => {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const x = ((clientX - rect.left) / rect.width) * width;
    const y = ((clientY - rect.top) / rect.height) * height;
    return { x: clamp(snap(x), 0, width), y: clamp(snap(y), 0, height) };
  };

  const handlePointerDown = (e, code) => {
    onSelect(code);
    if (!editMode) return;
    e.preventDefault();
    const move = (ev) => {
      const p = toLocal(ev.clientX, ev.clientY);
      if (p) onMove(code, p.x, p.y);
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
  };

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${width} ${height}`}
      style={{ width: '100%', height: 'auto', background: 'var(--bg-panel)', borderRadius: 8, touchAction: editMode ? 'none' : 'auto' }}
      role="img"
      aria-label="Factory floor map"
    >
      {zones.map((z) => (
        <g key={z.id}>
          <rect
            x={z.x} y={z.y} width={z.w} height={z.h}
            fill="none" stroke="var(--border)" strokeWidth={2} strokeDasharray={z.auto ? '8 4' : undefined} rx={8}
          />
          <text x={z.x + 10} y={z.y + 22} fill="var(--muted)" fontSize={15} fontWeight={600}>
            {z.name || z.id}{z.auto ? ' (auto)' : ''}
          </text>
        </g>
      ))}
      {nodes.map((n) => {
        const dim = dimmed && !dim.has(n.code);
        const selected = selectedCode === n.code;
        return (
          <g
            key={n.code}
            transform={`translate(${n.x},${n.y})`}
            opacity={dim ? 0.22 : 1}
            style={{ cursor: editMode ? 'grab' : 'pointer' }}
            onPointerDown={(e) => handlePointerDown(e, n.code)}
          >
            {n.alert && (
              <circle r={30} fill="none" stroke="#ef4444" strokeWidth={2} opacity={0.8}>
                <animate attributeName="r" values="24;34;24" dur="2s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.9;0.2;0.9" dur="2s" repeatCount="indefinite" />
              </circle>
            )}
            <circle
              r={20}
              fill={TONE_FILL[n.tone] || TONE_FILL.stale}
              stroke={selected ? '#f59e0b' : '#0b1220'}
              strokeWidth={selected ? 4 : 2}
            />
            <text textAnchor="middle" dy={7} fontSize={18} fill="#0b1220">{typeGlyph(n.machineType)}</text>
            <text textAnchor="middle" dy={40} fontSize={13} fontWeight={700} fill="var(--text)">{n.code}</text>
            <title>{`${n.code} — ${n.machineName} (${n.stateLabel})`}</title>
          </g>
        );
      })}
    </svg>
  );
}
