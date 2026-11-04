import { useState } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseBrowserClient } from '../lib/supabase';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function AdminLogin() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const supabase = getSupabaseBrowserClient();
      const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
      if (signInError) throw signInError;
      const { data: { session } } = await supabase.auth.getSession();
      const response = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      const profile = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(profile.detail || 'Unable to verify your account permissions.');
      if (!profile.is_admin) {
        await supabase.auth.signOut();
        throw new Error('This account is not authorised for Vortex administration.');
      }
      await router.push('/dashboard');
    } catch (err) {
      setError(err.message || 'Unable to sign in');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell admin-auth-shell">
      <section className="auth-panel">
        <div className="auth-brand"><span className="auth-mark">V</span><span>VORTEX <b>TECHNOLOGIES</b></span></div>
        <div className="auth-copy">
          <p className="eyebrow">SECURE ADMINISTRATION</p>
          <h1>Control with<br /><em>confidence.</em></h1>
          <p className="muted">Manage school onboarding and platform operations from one secure workspace.</p>
        </div>
        <form className="auth-form" onSubmit={submit}>
          <label htmlFor="admin-email">Administrator email</label>
          <input id="admin-email" type="email" autoComplete="username" placeholder="name@company.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <label htmlFor="admin-password">Password</label>
          <input id="admin-password" type="password" autoComplete="current-password" placeholder="Enter your password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="auth-submit" type="submit" disabled={loading}>{loading ? 'Verifying access…' : 'Sign in securely'} <span aria-hidden="true">→</span></button>
        </form>
        <p className="auth-foot">Access is restricted to provisioned Vortex administrators.</p>
      </section>
      <aside className="auth-aside">
        <div className="aside-orb" />
        <div className="aside-content">
          <span className="aside-kicker">VORTEX TECHNOLOGIES</span>
          <h2>Powering the<br />future of<br /><em>school operations.</em></h2>
          <div className="aside-points"><span>01 / Trusted identity</span><span>02 / Role-based access</span><span>03 / Operational clarity</span></div>
        </div>
        <span className="aside-footer">CHIKORO DIGITAL · ADMIN CONSOLE</span>
      </aside>
    </main>
  );
}
