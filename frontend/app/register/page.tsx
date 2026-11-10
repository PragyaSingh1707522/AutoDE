'use client';

import Link from 'next/link';
import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getApiUrl, setAccessToken } from '../../lib/auth';

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const response = await fetch(`${getApiUrl()}/auth/register`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password, organization_name: name }) });
      const data = await response.json();
      if (!response.ok) { setError(data.detail || 'Unable to create your account.'); return; }
      setAccessToken(data.access_token); router.replace('/');
    } catch { setError('Could not reach AutoDE. Check that the API is running.'); }
    finally { setBusy(false); }
  }
  return <main className="auth-shell"><section className="auth-card"><div className="brand"><span className="brandmark">A</span><span>AutoDE</span></div><h1>Create your workspace</h1><p className="sub">Your account starts as the organization owner.</p><form onSubmit={submit}><label>Organization name<input autoComplete="organization" required value={name} onChange={e => setName(e.target.value)}/></label><label>Email<input autoComplete="email" type="email" required value={email} onChange={e => setEmail(e.target.value)}/></label><label>Password<input autoComplete="new-password" type="password" minLength={10} required value={password} onChange={e => setPassword(e.target.value)}/><small>At least 10 characters</small></label>{error && <p className="auth-error">{error}</p>}<button className="auth-submit" disabled={busy}>{busy ? 'Creating…' : 'Create account'}</button></form><p className="auth-switch">Already have an account? <Link href="/login">Sign in</Link></p></section></main>;
}
