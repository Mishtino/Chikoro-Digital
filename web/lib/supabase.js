import { createClient } from '@supabase/supabase-js';

let client;
export function getSupabaseBrowserClient() {
  if (typeof window === 'undefined') throw new Error('Authentication is available in the browser only.');
  if (!client) {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    if (!url || !key) throw new Error('Sign-in is temporarily unavailable. Please contact your school.');
    client = createClient(url, key, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } });
  }
  return client;
}
