import { useState } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function PortalRegister() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const supabase = getSupabaseBrowserClient();
      const { data, error: signUpError } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: { emailRedirectTo: window.location.origin + '/portal/activate' },
      });
      if (signUpError) throw signUpError;
      if (data.session) {
        router.push('/portal/activate');
        return;
      }
      setMessage('Account created. Check your email and confirm your address. The confirmation link will take you to the secure activation step.');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-visual">
        <div className="brand-lockup"><span className="brand-mark">C</span><span>CHIKORO DIGITAL</span></div>
        <div className="visual-copy"><span className="eyebrow">Secure parent onboarding</span><h1>Stay connected to your child’s school journey.</h1><p>Create your secure sign-in, verify your email, then link your account with the one-time PIN issued by your school.</p></div>
        <div className="visual-foot">Simple. Secure. Connected.</div>
      </section>
      <section className="auth-panel"><div className="auth-card">
        <div className="form-eyebrow">Parent portal activation</div><h2>Create your account</h2>
        <p className="auth-subtitle">Ask your school for a guardian activation PIN before starting.</p>
        {error && <div className="auth-alert error" role="alert">{error}</div>}
        {message && <div className="auth-alert" role="status">{message}</div>}
        <form onSubmit={submit}>
          <div className="field"><label htmlFor="parent-email">Guardian email address</label><input id="parent-email" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="Enter the email recorded by your school" required /></div>
          <div className="field"><label htmlFor="parent-password">Create password</label><input id="parent-password" type="password" autoComplete="new-password" minLength={10} value={password} onChange={event => setPassword(event.target.value)} placeholder="At least 10 characters" required /></div>
          <button className="auth-button" type="submit" disabled={loading}>{loading ? 'Creating secure account…' : 'Create parent account'}</button>
        </form>
        <div className="auth-divider"></div>
        <div className="auth-links"><a href="/portal/login">Already have an account? Sign in</a></div>
        <p className="auth-note">Your guardian PIN is single-use and expires after seven days. Never share it with anyone other than the intended account holder.</p>
      </div></section>
    </main>
  );
}
