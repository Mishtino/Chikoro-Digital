import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseBrowserClient } from '../../lib/supabase';
import { api } from '../../lib/api';

export default function PortalRegister() {
  const router = useRouter();
  const [session, setSession] = useState(null);
  const [checking, setChecking] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [form, setForm] = useState({ school_code: '', student_number: '', pin: '', phone: '' });
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    const supabase = getSupabaseBrowserClient();
    supabase.auth.getSession().then(({ data: { session: current } }) => {
      if (mounted) { setSession(current); setChecking(false); }
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, current) => {
      if (mounted) setSession(current);
    });
    return () => { mounted = false; subscription.unsubscribe(); };
  }, []);

  async function createIdentity(e) {
    e.preventDefault(); setError(''); setMessage(''); setLoading(true);
    try {
      const { data, error: signupError } = await getSupabaseBrowserClient().auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${window.location.origin}/portal/register` },
      });
      if (signupError) throw signupError;
      if (data.session) setSession(data.session);
      else setMessage('Check your email and confirm your address. Then return here to enter the activation details from your school.');
    } catch (e) { setError(e.message || 'Unable to create your sign-in identity'); }
    finally { setLoading(false); }
  }

  async function activate(e) {
    e.preventDefault(); setError(''); setMessage(''); setLoading(true);
    try {
      await api('/portal/register', { method: 'POST', body: JSON.stringify(form) });
      setMessage('Your learner account is linked. Opening your portal…');
      await router.replace('/portal/fees');
    } catch (e) { setError(e.message || 'Unable to activate this learner account'); }
    finally { setLoading(false); }
  }

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    setSession(null);
  }

  function setField(key, value) { setForm((current) => ({ ...current, [key]: value })); }

  if (checking) return <main className="container"><section className="card">Checking your account…</section></main>;

  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div className="auth-brand"><span className="auth-mark">C</span><span>CHIKORO <b>DIGITAL</b></span></div>
        <div className="auth-copy">
          <p className="eyebrow">SECURE ACCOUNT ACTIVATION</p>
          <h1>Connect your<br /><em>school account.</em></h1>
          <p className="muted">Create your secure sign-in, verify your email, then link the learner record using the one-time PIN issued by your school.</p>
        </div>
        {error && <p className="auth-error" role="alert">{error}</p>}
        {message && <p className="success" role="status">{message}</p>}
        {!session ? (
          <form className="auth-form" onSubmit={createIdentity}>
            <label htmlFor="register-email">Email address</label>
            <input id="register-email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            <label htmlFor="register-password">Create password</label>
            <input id="register-password" type="password" minLength={8} autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            <button className="auth-submit" disabled={loading}>{loading ? 'Creating account…' : 'Create secure sign-in'} <span>→</span></button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={activate}>
            <p className="muted">Signed in as <b>{session.user.email}</b></p>
            <label htmlFor="school-code">School code</label>
            <input id="school-code" required value={form.school_code} onChange={(e) => setField('school_code', e.target.value)} />
            <label htmlFor="student-number">Student number</label>
            <input id="student-number" required value={form.student_number} onChange={(e) => setField('student_number', e.target.value)} />
            <label htmlFor="activation-pin">One-time activation PIN</label>
            <input id="activation-pin" required value={form.pin} onChange={(e) => setField('pin', e.target.value)} />
            <label htmlFor="phone">Phone (optional)</label>
            <input id="phone" value={form.phone} onChange={(e) => setField('phone', e.target.value)} />
            <button className="auth-submit" disabled={loading}>{loading ? 'Linking learner record…' : 'Activate learner account'} <span>→</span></button>
            <button type="button" className="auth-submit" onClick={signOut}>Use another email</button>
          </form>
        )}
        <p className="auth-foot"><a href="/portal/login">Already activated? Sign in</a></p>
      </section>
      <aside className="auth-aside"><div className="aside-orb" /><div className="aside-content"><span className="aside-kicker">VERIFIED SCHOOL ACCESS</span><h2>One verified identity.<br /><em>Your learner record.</em></h2><div className="aside-points"><span>01 / Verify your email</span><span>02 / Enter your school PIN</span><span>03 / Access your portal</span></div></div><span className="aside-footer">CHIKORO DIGITAL · EDUCATION, CONNECTED</span></aside>
    </main>
  );
}
