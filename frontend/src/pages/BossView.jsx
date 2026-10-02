import { useEffect, useState } from 'react';
import { api } from '../services/api';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import VoicePicker from '../components/VoicePicker';
import { speakText, speechSupported, stopSpeaking } from '../services/voice';

// Boss view: plain-language factory status for non-technical managers.
// Same data as the admin dashboard, zero jargon, verdict-first.
// The at-risk list is LIVE from GET /api/orders/at-risk (deterministic
// engine; AI delay estimates when ?ai=true and the key exists).
function machineCode(name) {
  const m = /^M-\d{3}/.exec(name || '');
  return m ? m[0] : String(name || '').slice(0, 12);
}

function toneForRisk(level) {
  if (level === 'HIGH') return 'bad';
  if (level === 'MEDIUM') return 'warn';
  return 'ok';
}

export default function BossView({ orders, production, incidents, machines, loading }) {
  const [risk, setRisk] = useState(null);
  const [riskError, setRiskError] = useState('');
  const [notifying, setNotifying] = useState('');
  const [notifyMsg, setNotifyMsg] = useState('');
  const [reading, setReading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.ordersAtRisk().then((r) => {
      if (!cancelled) setRisk(r);
    }).catch((err) => {
      if (!cancelled) setRiskError(err.message || 'Risk service offline — showing local estimate.');
    });
    return () => { cancelled = true; stopSpeaking(); };
  }, []);

  const now = new Date();
  const active = (orders || []).filter(
    (o) => !['COMPLETED', 'DONE', 'CANCELLED'].includes((o.status || '').toUpperCase()),
  );
  const open = (incidents || []).filter(
    (i) => !['RESOLVED', 'CLOSED'].includes((i.status || '').toUpperCase()),
  );
  const weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
  const breakdownsWeek = (incidents || []).filter((i) => i.created_at && new Date(i.created_at).getTime() >= weekAgo).length;

  // Live backend risk wins; local heuristic is the offline fallback.
  const liveRows = risk?.orders || null;
  const perOrder = active.map((o) => {
    const live = liveRows?.find((r) => r.order_id === o.id);
    const runs = (production || []).filter((p) => p.order_id === o.id);
    const target = runs.reduce((a, p) => a + (p.quantity_target || 0), 0) || o.quantity || 0;
    const done = runs.reduce((a, p) => a + (p.quantity_completed || 0), 0);
    const pct = target > 0 ? Math.round((done / target) * 100) : Math.round((o.progress || 0) * 100);
    if (live) {
      const tone = toneForRisk(live.risk_level);
      const verdict = live.risk_level === 'HIGH' ? 'High risk' : live.risk_level === 'MEDIUM' ? 'Watch' : 'On track';
      return { order: o, pct, verdict, tone, live };
    }
    const dl = o.deadline ? new Date(o.deadline) : null;
    const hoursLeft = dl ? (dl - now) / 3600000 : null;
    let verdict = 'On track';
    let tone = 'ok';
    if (open.some((i) => i.order_id === o.id)) { verdict = 'Blocked by a machine problem'; tone = 'bad'; }
    else if (hoursLeft !== null && hoursLeft < 0 && pct < 100) { verdict = 'Late'; tone = 'bad'; }
    else if (hoursLeft !== null && hoursLeft < 72 && pct < 100) { verdict = 'Due within 3 days'; tone = 'warn'; }
    else if (pct === 0) { verdict = 'Not started'; tone = 'warn'; }
    return { order: o, pct, verdict, tone, hoursLeft };
  });
  const atRisk = perOrder.filter((p) => p.tone !== 'ok').length;
  const attention = machines.filter((m) => open.some((i) => i.machine_id === m.id));

  const headline = loading
    ? 'Loading…'
    : open.length === 0 && atRisk === 0
      ? 'All clear — orders on track, machines running.'
      : `${open.length} machine problem${open.length === 1 ? '' : 's'}, ${atRisk} order${atRisk === 1 ? '' : 's'} need${atRisk === 1 ? 's' : ''} attention.`;

  const notify = async (orderId) => {
    setNotifying(orderId);
    setNotifyMsg('');
    try {
      const res = await api.notifyOrderRisk(orderId);
      setNotifyMsg(res.notified
        ? `Managers notified (${res.managers_notified}).`
        : (res.reason || 'No bell raised.'));
    } catch (err) {
      setNotifyMsg(err.message || 'Notify failed');
    } finally {
      setNotifying('');
    }
  };

  // Boss-home voice summary (uses the site-wide picked voice).
  const readStatus = () => {
    if (reading) {
      stopSpeaking();
      setReading(false);
      return;
    }
    const risky = perOrder.filter((p) => p.tone !== 'ok').slice(0, 3);
    const parts = [headline.replace(/—/g, '') + '.'];
    for (const r of risky) {
      parts.push(`${r.order.order_number} is ${r.verdict}. ${r.live?.reason || ''}`);
    }
    if (risky.length === 0) parts.push('No orders need attention.');
    setReading(true);
    const ok = speakText(parts.join(' '), { onend: () => setReading(false) });
    if (!ok) setReading(false);
  };

  return (
    <div>
      <section className="panel" role="status">
        <h2 style={{ fontSize: '1.2rem' }}>{headline}</h2>
        <p className="muted">
          Plain-language summary. Switch to Admin view for the full tables.{' '}
          {risk ? <StatusBadge tone={risk.source === 'ai' ? 'info' : 'warn'}>risk: {risk.source}</StatusBadge>
            : riskError ? <span className="muted">risk: local estimate</span> : null}
        </p>
        {speechSupported() && (
          <div className="no-print" style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
            <button type="button" className={reading ? 'btn-primary' : 'btn-secondary'} onClick={readStatus} title="Read this summary aloud">
              {reading ? '⏹ Stop' : '🔊 Read status aloud'}
            </button>
            <VoicePicker />
          </div>
        )}
      </section>

      <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <StatCard label="Orders on track" value={perOrder.length - atRisk} sub={`of ${perOrder.length} active`} loading={loading} />
        <StatCard label="Orders need attention" value={atRisk} sub="late, due soon, or blocked" loading={loading} />
        <StatCard label="Breakdowns this week" value={breakdownsWeek} sub="incidents raised" loading={loading} />
        <StatCard label="Machines down" value={attention.length} sub={attention.map((m) => machineCode(m.name)).join(', ') || 'none'} loading={loading} />
      </section>

      <section className="panel">
        <h2>Every active order, in one line</h2>
        {notifyMsg && <p className="muted" role="status">{notifyMsg}</p>}
        {loading ? <p className="muted">Loading…</p> : perOrder.length === 0 ? (
          <p className="muted">No active orders right now.</p>
        ) : (
          <ul className="task-list">
            {perOrder.slice(0, 10).map(({ order: o, pct, verdict, tone, live }) => (
              <li key={o.id} className="task-row">
                <div className="task-main">
                  <span className="cell-strong">{o.order_number}</span>
                  <span className="task-meta">{o.product || ''} · {o.customer_name || ''} · {pct}% done{o.deadline ? ` · due ${new Date(o.deadline).toLocaleDateString()}` : ''}</span>
                  {live && <span className="task-meta">{live.reason}{live.estimated_delay_hours != null ? ` · AI delay ~${live.estimated_delay_hours}h` : ''} <span className="cell-mono">{JSON.stringify(live.numbers)}</span></span>}
                </div>
                <div className="task-badges"><StatusBadge tone={tone}>{verdict}</StatusBadge></div>
                <div className="cell-actions">
                  {live && live.risk_level === 'HIGH' && (
                    <button type="button" className="btn-small" disabled={notifying === o.id} onClick={() => notify(o.id)}>
                      {notifying === o.id ? '…' : '🔔 Notify managers'}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
