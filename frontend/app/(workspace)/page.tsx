'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../lib/auth';
import { useIdentity } from '../../components/workspace-shell';
import type { Approval, Source } from '../../lib/types';

export default function OverviewPage() {
  const identity = useIdentity();
  const canWrite = identity.role === 'owner' || identity.role === 'analyst';
  const [sources, setSources] = useState<Source[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [sourceResponse, approvalResponse] = await Promise.all([apiFetch('/api/sources'), apiFetch('/api/approvals')]);
      if (!sourceResponse.ok || !approvalResponse.ok) throw new Error('Could not load workspace data.');
      setSources(await sourceResponse.json());
      setApprovals(await approvalResponse.json());
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load workspace data.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function upload(file?: File) {
    if (!file) return;
    setBusy(true); setError('');
    try {
      const form = new FormData(); form.append('file', file);
      const response = await apiFetch('/api/sources', { method: 'POST', body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Upload failed.');
      setAnswer(`${data.filename}: profiled ${data.row_count} rows.`);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Upload failed.'); }
    finally { setBusy(false); }
  }
  async function ask() {
    setBusy(true); setError('');
    try {
      const response = await apiFetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, language: 'en' }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Unable to answer that question.');
      setAnswer(data.answer);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to answer that question.'); }
    finally { setBusy(false); }
  }

  const rows = sources.reduce((sum, source) => sum + source.row_count, 0);
  const pendingApprovals = approvals.filter(item => item.status === 'pending').length;
  return <div className="page-stack">
    <div className="page-intro"><p className="sub">Bring your files. AutoDE profiles them for your organization.</p>{canWrite && <label className="upload"><input type="file" accept=".csv,.tsv" onChange={event => void upload(event.target.files?.[0])}/><span>＋ &nbsp; {busy ? 'Working…' : 'Upload files'}</span></label>}</div>
    {error && <div className="notice" role="alert">{error} <button onClick={() => void load()}>Retry</button></div>}
    <div className="stats"><article><small>CONNECTED SOURCES</small><strong>{loading ? '—' : sources.length.toString().padStart(2, '0')}</strong><span>Files in your workspace</span></article><article><small>ROWS PROFILED</small><strong>{loading ? '—' : rows.toLocaleString()}</strong><span>Across all your sources</span></article><article><small>NEEDS YOUR REVIEW</small><strong className={pendingApprovals ? 'amber' : ''}>{loading ? '—' : pendingApprovals.toString().padStart(2, '0')}</strong><span>Pending approvals</span></article></div>
    {loading ? <div className="panel state" role="status">Loading your data…</div> : <div className="grid">
      <section className="panel"><div className="panelhead"><div><h2>Your data sources</h2><p>Files profiled for this workspace</p></div><Link className="text-link" href="/sources">View all</Link></div>
        {sources.length === 0 ? <div className="empty"><div className="emptyicon">↥</div><b>Your workspace is ready</b><p>{canWrite ? 'Upload a CSV or TSV to create the first source profile.' : 'No data sources have been uploaded yet.'}</p></div> : <div className="source-list">{sources.slice(0, 5).map(source => <Link className="source source-link" key={source.id} href={`/sources/${source.id}`}><div className="fileicon">▤</div><div className="sourceinfo"><b>{source.filename}</b><small>{source.row_count.toLocaleString()} rows · {Object.keys(source.profile.columns).length} columns</small></div><span className="healthy">View profile →</span></Link>)}</div>}
      </section>
      {canWrite && <section className="panel assistant"><div className="panelhead"><div><h2>Ask your data</h2><p>Ask a question about your sources</p></div><span className="spark">✳</span></div><div className="chat"><div className="bot"><span>✳</span><p>{answer || 'Upload a file and ask me what’s inside.'}</p></div><div className="suggestions"><button onClick={() => setQuestion('Summarize my data')}>Summarize my data</button><button onClick={() => setQuestion('Which columns have missing values?')}>Find missing values</button></div></div><div className="askbox"><input value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => event.key === 'Enter' && void ask()} placeholder="Ask a question…"/><button onClick={() => void ask()} disabled={!question || busy}>↑</button></div><small className="lang">English · हिन्दी · ಕನ್ನಡ</small></section>}
    </div>}
  </div>;
}
