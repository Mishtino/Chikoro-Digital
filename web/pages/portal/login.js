import { useRouter } from 'next/router';
import { useState } from 'react';

export default function PortalLogin() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function submit(e) {
    e.preventDefault(); setError(''); setLoading(true);
    try {
      const form = new URLSearchParams(); form.append('username', email); form.append('password', password);
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/auth/login`, { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'We could not sign you in. Check your details and try again.');
      localStorage.setItem('token', data.access_token); router.push('/portal/fees');
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
          <div className="field"><label htmlFor="portal-email">Student ID or email</label><input id="portal-email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} placeholder="Enter your student ID or email" required /></div>
          <div className="field"><label htmlFor="portal-password">Password</label><input id="portal-password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Enter your password" required /></div>
          <button className="auth-button" type="submit" disabled={loading}>{loading ? 'Signing you in…' : 'Sign in to portal'}</button>
        </form>
        <div className="auth-divider"></div>
        <div className="auth-links"><span>New to the portal? <a href="/portal/register">Activate account</a></span><a href="/">Change school</a></div>
        <p className="auth-note">Your school-issued details are used to activate your account. If you need help, contact your school administrator.</p>
      </div></section>
    </main>
  );
}