import { useState } from 'react';
import { useRouter } from 'next/router';

export default function PortalRegister() {
  const router = useRouter();
  const [form, setForm] = useState({ school_code: '', student_number: '', pin: '', email: '', password: '', phone: '' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  async function submit(e) {
    e.preventDefault();
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/portal/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Registration failed');
      setSuccess('Registered. Please log in.');
      setTimeout(() => router.push('/portal/login'), 1200);
    } catch (err) {
      setError(err.message);
    }
  }
  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }
  return (
    <div className="container">
      <div className="card">
        <h1>Activate your portal account</h1>
        {error && <div className="error">{error}</div>}
        {success && <div className="success">{success}</div>}
        <form onSubmit={submit}>
          <input placeholder="School code" value={form.school_code} onChange={(e) => set('school_code', e.target.value)} />
          <input placeholder="Student ID (from slip)" value={form.student_number} onChange={(e) => set('student_number', e.target.value)} />
          <input placeholder="One-time PIN (from slip)" value={form.pin} onChange={(e) => set('pin', e.target.value)} />
          <input type="email" placeholder="Email (optional)" value={form.email} onChange={(e) => set('email', e.target.value)} />
          <input type="password" placeholder="Password" value={form.password} onChange={(e) => set('password', e.target.value)} />
          <input placeholder="Phone (optional)" value={form.phone} onChange={(e) => set('phone', e.target.value)} />
          <button type="submit">Activate</button>
        </form>
      </div>
    </div>
  );
}
