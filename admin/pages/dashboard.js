import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Dashboard() {
  const router = useRouter();
  const [schools, setSchools] = useState([]);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ code: '', name: '', province: '' });
  const [creating, setCreating] = useState(false);

  async function load() {
    const token = localStorage.getItem('token');
    if (!token) { router.push('/'); return; }
    try {
      const res = await fetch(`${API}/schools`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load schools');
      setSchools(data);
    } catch (e) { setError(e.message); }
  }

  useEffect(() => { load(); }, [router]);

  async function createSchool(e) {
    e.preventDefault();
    setCreating(true); setError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API}/schools`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Create failed');
      setForm({ code: '', name: '', province: '' });
      await load();
    } catch (e) { setError(e.message); }
    finally { setCreating(false); }
  }

  return (
    <div className="container">
      <div className="card">
        <h1>VortexTechPortal — Schools</h1>
        {error && <p style={{ color: 'red' }}>{error}</p>}
        <form onSubmit={createSchool} style={{ display: 'grid', gap: '.5rem', marginBottom: '1.5rem' }}>
          <input placeholder="School code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
          <input placeholder="School name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="Province" value={form.province} onChange={(e) => setForm({ ...form, province: e.target.value })} />
          <button type="submit" disabled={creating}>{creating ? 'Creating...' : 'Create school'}</button>
        </form>
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
