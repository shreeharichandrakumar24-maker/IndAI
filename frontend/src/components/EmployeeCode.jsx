import { useEffect, useState } from 'react';
import { api } from '../services/api';
import StatusBadge from './StatusBadge';

// Employee-code badge (Part 3). Readable EMP-001 style code next to a name,
// reused in tables, drawers, proposal cards and plan items. Fetches once per
// employee id (module cache); renders nothing while loading or when absent.
// Never shows email, username or anything secret (code only).
const cache = new Map();

export default function EmployeeCode({ employeeId }) {
  const [code, setCode] = useState(() => (employeeId ? cache.get(employeeId) || '' : ''));
  useEffect(() => {
    if (!employeeId || cache.has(employeeId)) return undefined;
    let cancelled = false;
    api.workerLoginInfo(employeeId).then((info) => {
      cache.set(employeeId, info?.employee_code || '');
      if (!cancelled) setCode(info?.employee_code || '');
    }).catch(() => {
      cache.set(employeeId, '');
    });
    return () => { cancelled = true; };
  }, [employeeId]);
  if (!code) return null;
  return <StatusBadge tone="neutral">{code}</StatusBadge>;
}
