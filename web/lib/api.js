import { getSupabaseBrowserClient } from './supabase';

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (typeof window !== 'undefined') {
    const { data, error } = await getSupabaseBrowserClient().auth.getSession();
    if (error) throw new Error('Your session could not be verified. Please sign in again.');
    const token = data.session?.access_token;
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText || 'The request could not be completed.');
  return data;
}
