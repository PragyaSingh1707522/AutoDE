'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { apiFetch, refreshAccessToken, setAccessToken } from '../lib/auth';
import { NAV_ITEMS, isNavActive } from '../lib/profile-utils.mjs';
import type { Identity } from '../lib/types';

const IdentityContext = createContext<Identity | null>(null);

export function useIdentity(): Identity {
  const identity = useContext(IdentityContext);
  if (!identity) throw new Error('useIdentity must be used inside the authenticated workspace');
  return identity;
}

function pageTitle(pathname: string): string {
  if (pathname === '/') return 'Overview';
  if (pathname === '/sources') return 'Data sources';
  if (pathname.startsWith('/sources/')) return 'Source details';
  if (pathname === '/quality') return 'Quality checks';
  if (pathname === '/approvals') return 'Approvals';
  return 'Workspace';
}

export default function WorkspaceShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadIdentity = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      if (!await refreshAccessToken()) {
        setAccessToken(null);
        router.replace('/login');
        return;
      }
      const response = await apiFetch('/auth/me');
      if (!response.ok) {
        setAccessToken(null);
        router.replace('/login');
        return;
      }
      setIdentity(await response.json());
    } catch {
      setError('We could not load your workspace. Check your connection and try again.');
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => { void loadIdentity(); }, [loadIdentity]);

  async function logout() {
    await apiFetch('/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    setAccessToken(null);
    router.replace('/login');
  }

  const contextValue = useMemo(() => identity, [identity]);
  if (loading) return <main className="loading" role="status">Restoring your session…</main>;
  if (error) return <main className="workspace-gate"><section className="panel"><h1>Workspace unavailable</h1><p>{error}</p><button className="button-primary" onClick={() => void loadIdentity()}>Try again</button></section></main>;
  if (!identity) return <main className="loading" role="status">Redirecting to sign in…</main>;

  return <IdentityContext.Provider value={contextValue}>
    <div className="workspace-shell">
      <aside className="app-sidebar">
        <Link href="/" className="brand"><span className="brandmark">A</span><span>AutoDE</span></Link>
        <div className="org">WORKSPACE <b>{identity.organization.name}</b></div>
        <nav aria-label="Workspace navigation">
          {NAV_ITEMS.map(item => <Link key={item.href} href={item.href} className="nav-link" aria-current={isNavActive(item.href, pathname) ? 'page' : undefined}>
            <span className="nav-icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span>
          </Link>)}
        </nav>
        <div className="sidebar-user"><div className="avatar">{identity.user.email.slice(0, 2).toUpperCase()}</div><div className="identity"><b>{identity.user.email}</b><small>{identity.role}</small></div></div>
      </aside>
      <div className="workspace-main">
        <header className="workspace-topbar">
          <div><p className="eyebrow">{identity.organization.name}</p><h1>{pageTitle(pathname)}</h1></div>
          <div className="topbar-account"><div><b>{identity.user.email}</b><small>{identity.role}</small></div><button className="logout" onClick={() => void logout()}>Log out</button></div>
        </header>
        <main className="workspace-content">{children}</main>
      </div>
    </div>
  </IdentityContext.Provider>;
}
