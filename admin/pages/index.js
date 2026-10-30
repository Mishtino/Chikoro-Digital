import { useState } from 'react';
import { useRouter } from 'next/router';
export default function AdminLogin() {
  const router = useRouter();
  const [email, setEmail] = useState('vortextech.co.zw');
  const [password, setPassword] = useState('Rhoda2003@ig');
  const [error, setError] = useState('');
  async function submit(e) {
    e.preventDefault();
    const form = new URLSearchParams();
    form.append('username', email); form.append('password', password);
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/auth/login`, { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) { setError(data.detail || 'Login failed'); return; }
    localStorage.setItem('token', data.access_token);
    router.push('/dashboard');
  }
  return (
    <div className="container">
      <div className="card">
        <h1>VortexTechPortal</h1>
        {error && <p style={{ color: 'red' }}>{error}</p>}
        <form onSubmit={submit}>
          <input type="email" placeholder="Admin email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="submit">Sign in</button>
        </form>
      </div>
    </div>
  );
}
