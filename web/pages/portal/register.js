import { useState } from 'react';
import { useRouter } from 'next/router';

export default function PortalRegister() {
  const router = useRouter();
  const [form, setForm] = useState({ school_code: '', student_number: '', pin: '', email: '', password: '', phone: '' });
  const [error, setError] = useState(''); const [success, setSuccess] = useState(''); const [loading, setLoading] = useState(false);
  async function submit(e) {
    e.preventDefault(); setError(''); setSuccess(''); setLoading(true);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/portal/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) });
      const data = await res.json(); if (!res.ok) throw new Error(data.detail || 'Registration could not be completed.');
      setSuccess('Your portal account has been activated. You can now sign in.'); setTimeout(() => router.push('/portal/login'), 1500);
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }
  function set(k,v){setForm(f=>({...f,[k]:v}));}
  return (
    <main className="auth-shell">
      <section className="auth-visual">
        <div className="brand-lockup"><span className="brand-mark">C</span><span>CHIKORO DIGITAL</span></div>
        <div className="visual-copy"><span className="eyebrow">Get started</span><h1>Your school journey, all in one place.</h1><p>Activate your portal with the details provided by your school. Once registered, you can securely access your school information online.</p></div>
        <div className="visual-foot">Simple. Secure. Connected.</div>
      </section>
      <section className="auth-panel"><div className="auth-card">
        <div className="form-eyebrow">Student account activation</div><h2>Create your access</h2><p className="auth-subtitle">Use the school code and one-time PIN printed on your registration slip.</p>
        {error && <div className="auth-alert error" role="alert">{error}</div>}{success && <div className="auth-alert success" role="status">{success}</div>}
        <form onSubmit={submit}>
          <div className="field"><label htmlFor="school-code">School code</label><input id="school-code" value={form.school_code} onChange={e=>set('school_code',e.target.value)} placeholder="Enter school code" required /></div>
          <div className="field"><label htmlFor="student-number">Student ID</label><input id="student-number" value={form.student_number} onChange={e=>set('student_number',e.target.value)} placeholder="ID from your registration slip" required /></div>
          <div className="field"><label htmlFor="activation-pin">One-time activation PIN</label><input id="activation-pin" value={form.pin} onChange={e=>set('pin',e.target.value)} placeholder="Enter your one-time PIN" required /></div>
          <div className="field"><label htmlFor="register-email">Email address <span style={{color:'#8a97a7',fontWeight:400}}>(optional)</span></label><input id="register-email" type="email" autoComplete="email" value={form.email} onChange={e=>set('email',e.target.value)} placeholder="you@example.com" /></div>
          <div className="field"><label htmlFor="register-password">Create password</label><input id="register-password" type="password" autoComplete="new-password" value={form.password} onChange={e=>set('password',e.target.value)} placeholder="Create a secure password" required minLength={8} /></div>
          <div className="field"><label htmlFor="register-phone">Phone number <span style={{color:'#8a97a7',fontWeight:400}}>(optional)</span></label><input id="register-phone" value={form.phone} onChange={e=>set('phone',e.target.value)} placeholder="Your contact number" /></div>
          <button className="auth-button" type="submit" disabled={loading}>{loading ? 'Activating account…' : 'Activate my account'}</button>
        </form>
        <div className="auth-links"><span>Already registered? <a href="/portal/login">Sign in</a></span></div>
        <p className="auth-note">Keep your activation PIN and password private. For assistance, contact your school office.</p>
      </div></section>
    </main>
  );
}