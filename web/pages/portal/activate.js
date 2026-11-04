import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function ParentActivate() {
  const router = useRouter();
  const [pin, setPin] = useState('');
  const [activationType, setActivationType] = useState('parent');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [email, setEmail] = useState('');

  useEffect(() => {
    if (router.isReady && router.query.type === 'student') setActivationType('student');
    else if (router.isReady && router.query.type === 'parent') setActivationType('parent');
  }, [router.isReady, router.query.type]);

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
      await api(activationType === 'student' ? '/auth/student/activate' : '/auth/parent/activate', {
        method: 'POST',
        body: JSON.stringify({ pin }),
      });
      router.replace(activationType === 'student' ? '/portal/fees' : '/portal/parent');
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
        <div className="visual-copy"><span className="eyebrow">Verified guardian access</span><h1>One final step to connect your family.</h1><p>Your school-issued PIN confirms that this account belongs to the student or guardian recorded by the school.</p></div>
        <div className="visual-foot">Your family information stays protected.</div>
      </section>
      <section className="auth-panel"><div className="auth-card">
        <div className="form-eyebrow">Portal account activation</div><h2>Verify your school link</h2>
        {email && <p className="auth-subtitle">Signed in as {email}</p>}
        <div className="field"><label htmlFor="activation-type">Account type</label><select id="activation-type" value={activationType} onChange={event => setActivationType(event.target.value)}><option value="parent">Parent / guardian</option><option value="student">Student</option></select></div>
        {error && <div className="auth-alert error" role="alert">{error}</div>}
        {loading ? <p role="status">Checking your secure session…</p> : <form onSubmit={submit}>
          <div className="field"><label htmlFor="guardian-pin">Eight-digit school-issued activation PIN</label><input id="guardian-pin" inputMode="numeric" autoComplete="one-time-code" maxLength={8} pattern="[0-9]{8}" value={pin} onChange={event => setPin(event.target.value.replace(/[^0-9]/g, '').slice(0, 8))} placeholder="Enter the PIN from your school" required /></div>
          <button className="auth-button" type="submit" disabled={submitting || pin.length !== 8}>{submitting ? 'Verifying school link…' : activationType === 'student' ? 'Activate student portal' : 'Activate parent portal'}</button>
        </form>}
        <div className="auth-divider"></div>
        <div className="auth-links"><button type="button" onClick={logout}>Sign out</button><a href="/portal/login">Return to sign in</a></div>
        <p className="auth-note">The PIN is single-use. Parent PINs expire after seven days; student PINs expire after thirty days. If it has expired, ask the school office to issue a new one.</p>
      </div></section>
    </main>
  );
}
