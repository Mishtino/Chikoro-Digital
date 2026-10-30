import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
export default function Dashboard() {
  const router = useRouter();
  const [schools, setSchools] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { router.push('/'); return; }
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/schools`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (r) => { if (!r.ok) throw new Error((await r.json()).detail); return r.json(); })
      .then(setSchools)
      .catch((e) => setError(e.message));
  }, [router]);
  return (
    <div className="container">
      <div className="card">
        <h1>Schools</h1>
        {error && <p style={{ color: 'red' }}>{error}</p>}
        <table>
          <thead><tr><th>Code</th><th>Name</th><th>Province</th><th>Status</th><th>Plan</th></tr></thead>
          <tbody>
            {schools.map((s) => (
              <tr key={s.id}><td>{s.code}</td><td>{s.name}</td><td>{s.province}</td><td>{s.status}</td><td>{s.plan}</td></tr>
            ))}
          </tbody>
        </table>
        <p style={{ marginTop: '1rem' }}><a href="#" onClick={() => { localStorage.removeItem('token'); router.push('/'); }}>Log out</a></p>
      </div>
    </div>
  );
}
