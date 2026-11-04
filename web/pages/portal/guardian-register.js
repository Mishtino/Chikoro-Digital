import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseBrowserClient } from '../../lib/supabase';
import { api } from '../../lib/api';

export default function GuardianRegister() {
  const router = useRouter();
  const [session, setSession] = useState(null);
  const [checking, setChecking] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [form, setForm] = useState({ school_code: '', contact_id: '', pin: '' });
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
        email, password,
        options: { emailRedirectTo: `${window.location.origin}/portal/guardian-register` },
      });
      if (signupError) throw signupError;
      if (data.session) setSession(data.session);
      else setMessage('Check your email, confirm your address, then return here to activate your guardian account.');
    } catch (e) { setError(e.message || 'Unable to create your sign-in identity'); }
    finally { setLoading(false); }
  }

  async function activate(e) {
    e.preventDefault(); setError(''); setMessage(''); setLoading(true);
    try {
      await api('/portal/guardian/register', {
        method: 'POST',
        body: JSON.stringify({ ...form, contact_id: Number(form.contact_id) }),
      });
      setMessage('Your verified guardian account is active. Opening the family portal…');
      await router.replace('/portal/fees');
    } catch (e) { setError(e.message || 'Unable to activate your guardian account'); }
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
          <p className="eyebrow">PARENT & GUARDIAN ACCESS</p>
          <h1>Your family,<br /><em>connected.</em></h1>
          <p className="muted">Create a secure sign-in, confirm your email and activate access using the contact ID and one-time PIN issued by your school.</p>
        </div>
        {error && <p className="auth-error" role="alert">{error}</p>}
        {message && <p className="success" role="status">{message}</p>}
        {!session ? (
          <form className="auth-form" onSubmit={createIdentity}>
            <label htmlFor="guardian-email">Email address registered with your school</label>
            <input id="guardian-email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            <label htmlFor="guardian-password">Create password</label>
            <input id="guardian-password" type="password" minLength={8} autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            <button className="auth-submit" disabled={loading}>{loading ? 'Creating account…' : 'Create secure sign-in'} <span>→</span></button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={activate}>
            <p className="muted">Signed in as <b>{session.user.email}</b></p>
            <label htmlFor="guardian-school">School code</label>
            <input id="guardian-school" required value={form.school_code} onChange={(e) => setField('school_code', e.target.value)} />
            <label htmlFor="guardian-contact">Guardian contact ID</label>
            <input id="guardian-contact" type="number" min="1" required value={form.contact_id} onChange={(e) => setField('contact_id', e.target.value)} />
            <label htmlFor="guardian-pin">One-time activation PIN</label>
            <input id="guardian-pin" inputMode="numeric" autoComplete="one-time-code" required value={form.pin} onChange={(e) => setField('pin', e.target.value)} />
            <button className="auth-submit" disabled={loading}>{loading ? 'Verifying school record…' : 'Activate guardian account'} <span>→</span></button>
            <button type="button" className="auth-submit" onClick={signOut}>Use another email</button>
          </form>
        )}
        <p className="auth-foot"><a href="/portal/login">Already activated? Sign in</a></p>
      </section>
      <aside className="auth-aside">
        <div className="aside-orb" />
        <div className="aside-content">
          <span className="aside-kicker">VERIFIED FAMILY ACCESS</span>
          <h2>One trusted link.<br /><em>Every learner you support.</em></h2>
          <div className="aside-points"><span>01 / School-verified contact</span><span>02 / One-time PIN</span><span>03 / Family fee visibility</span></div>
        </div>
        <span className="aside-footer">CHIKORO DIGITAL · EDUCATION, CONNECTED</span>
      </aside>
    </main>
  );
}
