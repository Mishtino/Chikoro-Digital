import { useState } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseBrowserClient } from '../../lib/supabase';
import { api } from '../../lib/api';

export default function PortalLogin() {
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
      const { error: signInError } = await getSupabaseBrowserClient().auth.signInWithPassword({ email, password });
      if (signInError) throw signInError;
      const profile = await api('/auth/me');
      if (!['student', 'parent', 'admin'].includes(profile.role)) {
        await getSupabaseBrowserClient().auth.signOut();
        throw new Error('This account does not have student or parent portal access.');
      }
      await router.push('/portal/fees');
    } catch (err) {
      setError(err.message || 'Unable to sign in');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div className="auth-brand"><span className="auth-mark">C</span><span>CHIKORO <b>DIGITAL</b></span></div>
        <div className="auth-copy">
          <p className="eyebrow">STUDENT & PARENT PORTAL</p>
          <h1>Your school,<br /><em>within reach.</em></h1>
          <p className="muted">Access fee statements, payment information and your school updates securely.</p>
        </div>
        <form className="auth-form" onSubmit={submit}>
          <label htmlFor="portal-email">Email address</label>
          <input id="portal-email" type="email" autoComplete="username" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <label htmlFor="portal-password">Password</label>
          <input id="portal-password" type="password" autoComplete="current-password" placeholder="Enter your password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="auth-submit" type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign in to your portal'} <span aria-hidden="true">→</span></button>
        </form>
        <p className="auth-foot">Your account is managed by your school. Contact your school administrator if you need access.</p><p className="auth-foot"><a href="/portal/guardian-register">Parent or guardian? Activate your account</a></p>
      </section>
      <aside className="auth-aside">
        <div className="aside-orb" />
        <div className="aside-content">
          <span className="aside-kicker">CONNECTED LEARNING</span>
          <h2>One place for<br />the things that<br /><em>matter at school.</em></h2>
          <div className="aside-points"><span>01 / Fee visibility</span><span>02 / Secure access</span><span>03 / School connection</span></div>
        </div>
        <span className="aside-footer">CHIKORO DIGITAL · EDUCATION, CONNECTED</span>
      </aside>
    </main>
  );
}
