import { getSupabaseBrowserClient } from './supabase';

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function api(path, options = {}) {
  const { data: { session }, error } = await getSupabaseBrowserClient().auth.getSession();
  if (error) throw new Error('Unable to read your sign-in session.');
  if (!session?.access_token) throw new Error('Your session has expired. Please sign in again.');

  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
    Authorization: `Bearer ${session.access_token}`,
  };
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText || 'Request failed');
  return data;
}
