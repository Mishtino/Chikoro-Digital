import { useRouter } from 'next/router';
import { useState } from 'react';
import { api } from '../../lib/api';

export default function PortalLogin() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  async function submit(e) {
    e.preventDefault();
    try {
      const form = new URLSearchParams();
      form.append('username', email);
      form.append('password', password);
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/auth/login`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Login failed');
      localStorage.setItem('token', data.access_token);
      router.push('/portal/fees');
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <div className="container">
      <div className="card">
        <h1>Student / Parent Login</h1>
        {error && <div className="error">{error}</div>}
        <form onSubmit={submit}>
          <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="submit">Log in</button>
        </form>
        <p><a href="/portal/register">Register with your slip</a></p>
      </div>
    </div>
  );
}
