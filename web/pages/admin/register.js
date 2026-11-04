import { useState } from 'react';
import { createClient } from '@supabase/supabase-js';

const ADMIN_EMAIL = 'msirewu56@gmail.com';

function getClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error('Account registration is temporarily unavailable. Please contact support.');
  return createClient(url, key, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } });
}

export default function AdminRegister() {
  const [email] = useState(ADMIN_EMAIL);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError(''); setMessage('');
    if (password.length < 12) return setError('Use a password with at least 12 characters.');
    if (password !== confirm) return setError('The passwords do not match.');
    setLoading(true);
    try {
      const { data, error: signupError } = await getClient().auth.signUp({
        email: ADMIN_EMAIL,
        password,
        options: { emailRedirectTo: window.location.origin + '/admin/register?verified=1' },
      });
      if (signupError) throw signupError;
      setMessage(data.session
        ? 'Your sign-in identity has been created. Check your email for any confirmation request. Administrator access is activated separately after verification.'
        : 'Registration started. Check msirewu56@gmail.com and open the confirmation link. Administrator access is activated separately after verification.');
      setPassword(''); setConfirm('');
    } catch (err) {
      setError(err.message || 'Unable to create the account. If you already registered, check your email or contact support.');
    } finally { setLoading(false); }
  }

  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: '#f1f4fb', fontFamily: 'Arial, sans-serif' }}>
      <section style={{ width: '100%', maxWidth: 480, background: '#fff', padding: 32, borderRadius: 16, boxShadow: '0 12px 40px rgba(15,23,42,.08)' }}>
        <p style={{ color: '#64748b', fontSize: 12, letterSpacing: 2, fontWeight: 700 }}>CHIKORO DIGITAL · ADMINISTRATION</p>
        <h1 style={{ fontSize: 30, marginBottom: 8 }}>Create administrator sign-in</h1>
        <p style={{ color: '#475569', lineHeight: 1.6 }}>Create the secure sign-in identity for the designated administrator. This does not grant administrator privileges by itself. Access is activated only after email verification and a separate server-side account link.</p>
        {error && <p role="alert" style={{ background: '#fef2f2', color: '#b91c1c', padding: 12, borderRadius: 8 }}>{error}</p>}
        {message && <p role="status" style={{ background: '#ecfdf5', color: '#047857', padding: 12, borderRadius: 8 }}>{message}</p>}
        <form onSubmit={submit}>
          <label htmlFor="admin-email" style={{ display: 'block', margin: '18px 0 8px', fontWeight: 600 }}>Administrator email</label>
          <input id="admin-email" type="email" value={email} readOnly style={{ width: '100%', boxSizing: 'border-box', padding: 14, border: '1px solid #cbd5e1', borderRadius: 8, background: '#f8fafc' }} />
          <label htmlFor="admin-password" style={{ display: 'block', margin: '18px 0 8px', fontWeight: 600 }}>Create password</label>
          <input id="admin-password" type="password" autoComplete="new-password" minLength={12} required value={password} onChange={e => setPassword(e.target.value)} style={{ width: '100%', boxSizing: 'border-box', padding: 14, border: '1px solid #cbd5e1', borderRadius: 8 }} />
          <label htmlFor="admin-confirm" style={{ display: 'block', margin: '18px 0 8px', fontWeight: 600 }}>Confirm password</label>
          <input id="admin-confirm" type="password" autoComplete="new-password" minLength={12} required value={confirm} onChange={e => setConfirm(e.target.value)} style={{ width: '100%', boxSizing: 'border-box', padding: 14, border: '1px solid #cbd5e1', borderRadius: 8 }} />
          <button type="submit" disabled={loading} style={{ width: '100%', marginTop: 24, padding: 15, border: 0, borderRadius: 8, color: '#fff', background: '#111827', fontSize: 16, fontWeight: 600 }}>{loading ? 'Creating account…' : 'Create administrator sign-in'}</button>
        </form>
        <p style={{ color: '#64748b', fontSize: 13, marginTop: 20 }}>Keep your password private. Never send it to anyone by email or chat.</p>
        <a href="/portal/login" style={{ color: '#1d4ed8' }}>Return to sign in</a>
      </section>
    </main>
  );
}
