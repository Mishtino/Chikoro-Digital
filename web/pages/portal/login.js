import { useRouter } from 'next/router';
import { useState } from 'react';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function PortalLogin() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function submit(e) {
    e.preventDefault(); setError(''); setLoading(true);
    try {
      const supabase = getSupabaseBrowserClient();
      const { data, error: signInError } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
      if (signInError) throw signInError;
      const accessToken = data.session?.access_token;
      if (!accessToken) throw new Error('A secure session could not be created. Please try again.');
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/auth/supabase/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const profile = await response.json();
      if (!response.ok) {
        if (response.status === 403 && profile.detail === 'Account is not activated for Chikoro Digital') { router.push('/portal/activate'); return; }
        await supabase.auth.signOut();
        throw new Error(profile.detail || 'Your account is not yet activated. Contact your school administrator.');
      }
      if (profile.role === 'parent') { router.push('/portal/parent'); return; }
      if (['owner', 'headmaster'].includes(profile.role) && !profile.is_admin && profile.school_id) { router.push('/school-admin/staff'); return; }
      if (profile.role !== 'student') { await supabase.auth.signOut(); throw new Error('This account does not have portal access.'); }
      router.push('/portal/fees');
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }
  return (
    <main className="auth-shell">
      <section className="auth-visual">
        <div className="brand-lockup"><span className="brand-mark">C</span><span>CHIKORO DIGITAL</span></div>
        <div className="visual-copy"><span className="eyebrow">Your school, connected</span><h1>Learning starts with a connected community.</h1><p>One simple place for students and parents to stay informed, follow school fees and keep up with the school journey.</p></div>
        <div className="visual-foot">A smarter school experience · Chikoro Digital</div>
      </section>
      <section className="auth-panel"><div className="auth-card">
        <div className="form-eyebrow">Student & parent portal</div><h2>Welcome back</h2><p className="auth-subtitle">Sign in to continue to your school account.</p>
        {error && <div className="auth-alert error" role="alert">{error}</div>}
        <form onSubmit={submit}>
          <div className="field"><label htmlFor="portal-email">Email address</label><input id="portal-email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} placeholder="Enter your email address" required /></div>
          <div className="field"><label htmlFor="portal-password">Password</label><input id="portal-password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Enter your password" required /></div>
          <button className="auth-button" type="submit" disabled={loading}>{loading ? 'Signing you in…' : 'Sign in to portal'}</button>
        </form>
        <div className="auth-divider"></div>
        <div className="auth-links"><span>New here? <a href="/portal/student-register">Student activation</a> · <a href="/portal/register">Parent activation</a></span><a href="/">Change school</a></div>
        <p className="auth-note">Your school-issued details are used to activate your account. If you need help, contact your school administrator.</p>
      </div></section>
    </main>
  );
}