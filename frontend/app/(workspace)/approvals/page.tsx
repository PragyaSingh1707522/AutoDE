'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../../lib/auth';
import { useIdentity } from '../../../components/workspace-shell';
import type { Approval } from '../../../lib/types';

const STATUS_ORDER = ['pending', 'approved', 'rejected'];

export default function ApprovalsPage() {
  const identity = useIdentity();
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await apiFetch('/api/approvals');
      if (!response.ok) throw new Error('Could not load approval requests.');
      setApprovals(await response.json());
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load approval requests.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function decide(id: string, approved: boolean) {
    setBusyId(id); setError('');
    try {
      const response = await apiFetch(`/api/approvals/${id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved }) });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'The server rejected this decision.');
      }
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update approval.'); }
    finally { setBusyId(''); }
  }

  const statuses = [...STATUS_ORDER, ...new Set(approvals.map(item => item.status).filter(status => !STATUS_ORDER.includes(status)))];
  return <div className="page-stack">
    <p className="sub">Review source changes and see previous decisions.</p>
    {error && <div className="notice" role="alert">{error} <button onClick={() => void load()}>Retry</button></div>}
    {loading ? <div className="panel state" role="status">Loading approval requests…</div> : approvals.length === 0 ? <div className="panel empty-state"><h2>No approval requests</h2><p>When a source change needs review, it will appear here.</p></div> : statuses.map(status => {
      const items = approvals.filter(item => item.status === status);
      if (!items.length) return null;
      return <section className="panel approval-group" key={status}><div className="panelhead"><div><h2>{status[0].toUpperCase() + status.slice(1)}</h2><p>{items.length} request{items.length === 1 ? '' : 's'}</p></div><span className="pill">{items.length}</span></div>
        {items.map(item => <article className="approval-row" key={item.id}><div className="approval-copy"><b>{item.action.replaceAll('_', ' ')}</b><p>{item.reason}</p><small>Request {item.id}</small></div><span className={`status-label status-${item.status}`}>{item.status}</span>{identity.role === 'owner' && item.status === 'pending' && <div className="approval-actions"><button className="reject" disabled={busyId === item.id} onClick={() => void decide(item.id, false)}>Reject</button><button className="approve" disabled={busyId === item.id} onClick={() => void decide(item.id, true)}>{busyId === item.id ? 'Saving…' : 'Approve'}</button></div>}</article>)}
      </section>;
    })}
  </div>;
}
