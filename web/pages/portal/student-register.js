import { useState } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function StudentRegister() {
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
        options: { emailRedirectTo: window.location.origin + '/portal/activate?type=student' },
      });
      if (signUpError) throw signUpError;
      if (data.session) {
        router.push('/portal/activate?type=student');
        return;
      }
      setMessage('Account created. Check your school-registered email and confirm it. The confirmation link will take you to student activation.');
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
        <div className="visual-copy"><span className="eyebrow">Student portal onboarding</span><h1>Your learning journey, connected.</h1><p>Create a secure sign-in using the email address registered by your school, verify it, then enter your student activation PIN.</p></div>
        <div className="visual-foot">Simple. Secure. Connected.</div>
      </section>
      <section className="auth-panel"><div className="auth-card">
        <div className="form-eyebrow">Student portal activation</div><h2>Create your student account</h2>
        <p className="auth-subtitle">Your school must have registered this email address and issued you an activation PIN.</p>
        {error && <div className="auth-alert error" role="alert">{error}</div>}
        {message && <div className="auth-alert" role="status">{message}</div>}
        <form onSubmit={submit}>
          <div className="field"><label htmlFor="student-email">School-registered email</label><input id="student-email" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="Enter your registered email" required /></div>
          <div className="field"><label htmlFor="student-password">Create password</label><input id="student-password" type="password" autoComplete="new-password" minLength={10} value={password} onChange={event => setPassword(event.target.value)} placeholder="At least 10 characters" required /></div>
          <button className="auth-button" type="submit" disabled={loading}>{loading ? 'Creating secure account…' : 'Create student account'}</button>
        </form>
        <div className="auth-divider"></div>
        <div className="auth-links"><a href="/portal/login">Already have an account? Sign in</a></div>
        <p className="auth-note">If your email or activation PIN is not recognised, contact your school office. Never share your PIN with anyone.</p>
      </div></section>
    </main>
  );
}
