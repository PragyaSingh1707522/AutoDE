'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../../lib/auth';
import { profileWarnings } from '../../../lib/profile-utils.mjs';
import type { Source } from '../../../lib/types';

export default function QualityPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await apiFetch('/api/sources');
      if (!response.ok) throw new Error('Could not load source profiles.');
      setSources(await response.json());
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load source profiles.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return <div className="page-stack">
    <p className="sub">Quality signals calculated from the profiles available in your workspace.</p>
    {error && <div className="notice" role="alert">{error} <button onClick={() => void load()}>Retry</button></div>}
    {loading ? <div className="panel state" role="status">Loading profile quality…</div> : sources.length === 0 ? <div className="panel empty-state"><h2>No profiles to check</h2><p>Quality checks will appear after source files have been profiled.</p><Link className="text-link" href="/">Go to overview</Link></div> : <div className="quality-list">{sources.map(source => {
      const warnings = profileWarnings(source);
      const missingTotal = warnings.missing.reduce((sum, item) => sum + item.count, 0);
      const repeatedTotal = warnings.repeatedValues.reduce((sum, item) => sum + item.count, 0);
      return <section className="panel quality-card" key={source.id}>
        <div className="panelhead"><div><h2><Link href={`/sources/${source.id}`} className="text-link">{source.filename}</Link></h2><p>{source.row_count.toLocaleString()} rows · {Object.keys(source.profile.columns).length} columns</p></div><span className={missingTotal || repeatedTotal ? 'pill warning-pill' : 'pill'}>{missingTotal || repeatedTotal ? 'Profile warnings' : 'No profile warnings'}</span></div>
        <div className="quality-columns"><div><h3>Missing values</h3>{warnings.missing.length ? <ul>{warnings.missing.map(item => <li key={item.column}><b>{item.column}</b><span>{item.count.toLocaleString()} missing</span></li>)}</ul> : <p className="quality-ok">No missing values recorded in this profile.</p>}</div>
          <div><h3>Repeated values</h3>{warnings.repeatedValues.length ? <ul>{warnings.repeatedValues.map(item => <li key={item.column}><b>{item.column}</b><span>{item.count.toLocaleString()} repeated non-empty values</span></li>)}</ul> : <p className="quality-ok">No repeated non-empty column values in this profile.</p>}<p className="quality-note">Counts come from row and distinct-value profile metrics; they do not indicate duplicate records.</p></div></div>
        <div className="later-phase"><b>Whole-row duplicate detection</b><span>Coming in a later phase</span></div>
      </section>;
    })}</div>}
  </div>;
}
