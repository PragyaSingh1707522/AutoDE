'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../../../../lib/auth';
import { sourceVersions } from '../../../../lib/profile-utils.mjs';
import type { Source } from '../../../../lib/types';

export default function SourceDetailPage() {
  const params = useParams<{ id: string }>();
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await apiFetch('/api/sources');
      if (!response.ok) throw new Error('Could not load the source profile.');
      setSources(await response.json());
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load the source profile.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const source = sources.find(item => item.id === params.id);
  const versions = useMemo(() => sourceVersions(sources), [sources]);

  return <div className="page-stack">
    <Link className="text-link" href="/sources">← Back to data sources</Link>
    {error && <div className="notice" role="alert">{error} <button onClick={() => void load()}>Retry</button></div>}
    {loading ? <div className="panel state" role="status">Loading source profile…</div> : !source ? <div className="panel empty-state"><h2>Source not found</h2><p>This file may have been removed or may belong to another organization.</p></div> : <>
      <section className="panel detail-summary"><div><p className="eyebrow">SOURCE PROFILE</p><h2>{source.filename}</h2></div><div className="detail-facts"><span>{source.row_count.toLocaleString()} rows</span><span>{Object.keys(source.profile.columns).length} columns</span><span>Version {versions.get(source.id)}</span><span>Uploaded {new Date(source.created_at).toLocaleString()}</span></div></section>
      <section className="panel table-panel"><div className="panelhead"><div><h2>Column profile</h2><p>Inferred directly from the uploaded file</p></div></div><div className="table-scroll"><table><thead><tr><th>Column</th><th>Inferred type</th><th>Missing values</th><th>Distinct values</th></tr></thead><tbody>{Object.entries(source.profile.columns).map(([name, metrics]) => <tr key={name}><td>{name}</td><td><span className="type-pill">{metrics.inferred_type}</span></td><td>{metrics.null_count.toLocaleString()}</td><td>{metrics.distinct_count.toLocaleString()}</td></tr>)}</tbody></table></div></section>
    </>}
  </div>;
}
