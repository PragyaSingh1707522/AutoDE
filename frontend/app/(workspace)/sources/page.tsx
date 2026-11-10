'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../../lib/auth';
import { sourceVersions } from '../../../lib/profile-utils.mjs';
import type { Source } from '../../../lib/types';

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await apiFetch('/api/sources');
      if (!response.ok) throw new Error('Could not load data sources.');
      setSources(await response.json());
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load data sources.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const versions = sourceVersions(sources);

  return <div className="page-stack">
    <p className="sub">Uploaded files and their inferred profiles.</p>
    {error && <div className="notice" role="alert">{error} <button onClick={() => void load()}>Retry</button></div>}
    {loading ? <div className="panel state" role="status">Loading data sources…</div> : sources.length === 0 ? <div className="panel empty-state"><h2>No sources yet</h2><p>Uploaded CSV and TSV files will appear here with their profile and version.</p><Link className="text-link" href="/">Go to overview</Link></div> :
      <section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>File name</th><th>Rows</th><th>Columns</th><th>Uploaded</th><th>Version</th></tr></thead><tbody>{sources.map(source => <tr key={source.id}><td><Link className="text-link" href={`/sources/${source.id}`}>{source.filename}</Link></td><td>{source.row_count.toLocaleString()}</td><td>{Object.keys(source.profile.columns).length}</td><td>{new Date(source.created_at).toLocaleString()}</td><td>v{versions.get(source.id)}</td></tr>)}</tbody></table></div><p className="table-note">Versions are numbered from upload history for each filename.</p></section>}
  </div>;
}
