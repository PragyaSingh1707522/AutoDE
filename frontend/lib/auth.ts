const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
let accessToken: string | null = null;
let pendingRefresh: Promise<string | null> | null = null;

export function setAccessToken(value: string | null) { accessToken = value; }
export function getApiUrl() { return API; }

export async function refreshAccessToken(): Promise<string | null> {
  if (pendingRefresh) return pendingRefresh;
  pendingRefresh = (async () => {
    try {
      const response = await fetch(`${API}/auth/refresh`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      if (!response.ok) { accessToken = null; return null; }
      const data = await response.json();
      accessToken = data.access_token;
      return accessToken;
    } catch { accessToken = null; return null; }
    finally { pendingRefresh = null; }
  })();
  return pendingRefresh;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = () => {
    const headers = new Headers(init.headers);
    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
    return fetch(`${API}${path}`, { ...init, headers, credentials: 'include' });
  };
  let response = await send();
  if (response.status === 401 && !path.startsWith('/auth/')) {
    if (await refreshAccessToken()) response = await send();
    if (response.status === 401 && typeof window !== 'undefined') window.location.assign('/login');
  }
  return response;
}
