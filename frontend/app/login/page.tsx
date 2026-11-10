'use client';

import Link from 'next/link';
import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getApiUrl, setAccessToken } from '../../lib/auth';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const response = await fetch(`${getApiUrl()}/auth/login`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
      const data = await response.json();
      if (!response.ok) { setError(data.detail || 'Unable to sign in.'); return; }
      setAccessToken(data.access_token); router.replace('/');
    } catch { setError('Could not reach AutoDE. Check that the API is running.'); }
    finally { setBusy(false); }
  }
  return <main className="auth-shell"><section className="auth-card"><div className="brand"><span className="brandmark">A</span><span>AutoDE</span></div><h1>Welcome back</h1><p className="sub">Sign in to your organization workspace.</p><form onSubmit={submit}><label>Email<input autoComplete="email" type="email" required value={email} onChange={e => setEmail(e.target.value)}/></label><label>Password<input autoComplete="current-password" type="password" required value={password} onChange={e => setPassword(e.target.value)}/></label>{error && <p className="auth-error">{error}</p>}<button className="auth-submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></form><p className="auth-switch">New to AutoDE? <Link href="/register">Create an account</Link></p></section></main>;
}
