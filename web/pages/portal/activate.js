import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function ParentActivate() {
  const router = useRouter();
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [email, setEmail] = useState('');

  useEffect(() => {
    let active = true;
    getSupabaseBrowserClient().auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return;
      if (sessionError || !data.session) {
        setError('Verify your email first, then sign in to complete activation.');
        setLoading(false);
        return;
      }
      setEmail(data.session.user.email || '');
      setLoading(false);
    }).catch(() => {
      if (active) {
        setError('Your secure session could not be loaded. Please sign in again.');
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, []);

  async function submit(event) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await api('/auth/parent/activate', {
        method: 'POST',
        body: JSON.stringify({ pin }),
      });
      router.replace('/portal/parent');
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  async function logout() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  return (
    <main className="auth-shell">
      <section className="auth-visual">
        <div className="brand-lockup"><span className="brand-mark">C</span><span>CHIKORO DIGITAL</span></div>
        <div className="visual-copy"><span className="eyebrow">Verified guardian access</span><h1>One final step to connect your family.</h1><p>Your school-issued PIN confirms that this account belongs to the guardian recorded against the learner.</p></div>
        <div className="visual-foot">Your family information stays protected.</div>
      </section>
      <section className="auth-panel"><div className="auth-card">
        <div className="form-eyebrow">Parent account activation</div><h2>Verify your guardian link</h2>
        {email && <p className="auth-subtitle">Signed in as {email}</p>}
        {error && <div className="auth-alert error" role="alert">{error}</div>}
        {loading ? <p role="status">Checking your secure session…</p> : <form onSubmit={submit}>
          <div className="field"><label htmlFor="guardian-pin">Eight-digit activation PIN</label><input id="guardian-pin" inputMode="numeric" autoComplete="one-time-code" maxLength={8} pattern="[0-9]{8}" value={pin} onChange={event => setPin(event.target.value.replace(/[^0-9]/g, '').slice(0, 8))} placeholder="Enter the PIN from your school" required /></div>
          <button className="auth-button" type="submit" disabled={submitting || pin.length !== 8}>{submitting ? 'Verifying guardian link…' : 'Activate parent portal'}</button>
        </form>}
        <div className="auth-divider"></div>
        <div className="auth-links"><button type="button" onClick={logout}>Sign out</button><a href="/portal/login">Return to sign in</a></div>
        <p className="auth-note">The PIN is single-use and expires seven days after your school issues it. If it has expired, ask the school office to issue a new one.</p>
      </div></section>
    </main>
  );
}
