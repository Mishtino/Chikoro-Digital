import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Dashboard() {
  const router = useRouter();
  const [schools, setSchools] = useState([]);
  const [error, setError] = useState('');
  const [schoolForm, setSchoolForm] = useState({ code: '', name: '', province: '' });
  const [creatingSchool, setCreatingSchool] = useState(false);
  const [adminForm, setAdminForm] = useState({ school_id: '', email: '', full_name: '', password: '', role: 'owner' });
  const [creatingAdmin, setCreatingAdmin] = useState(false);
  const [adminMsg, setAdminMsg] = useState('');

  async function load() {
    const token = localStorage.getItem('token');
    if (!token) { router.push('/'); return; }
    try {
      const res = await fetch(`${API}/schools`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load schools');
      setSchools(data);
      if (!adminForm.school_id && data.length) setAdminForm((f) => ({ ...f, school_id: data[0].id }));
    } catch (e) { setError(e.message); }
  }

  useEffect(() => { load(); }, [router]);

  async function createSchool(e) {
    e.preventDefault();
    setCreatingSchool(true); setError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API}/schools`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(schoolForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Create failed');
      setSchoolForm({ code: '', name: '', province: '' });
      await load();
    } catch (e) { setError(e.message); }
    finally { setCreatingSchool(false); }
  }

  async function createAdmin(e) {
    e.preventDefault();
    setCreatingAdmin(true); setError(''); setAdminMsg('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API}/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ...adminForm, school_id: Number(adminForm.school_id) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Create admin failed');
      setAdminMsg(`Created ${data.email} (${data.role})`);
      setAdminForm((f) => ({ ...f, email: '', full_name: '', password: '' }));
    } catch (e) { setError(e.message); }
    finally { setCreatingAdmin(false); }
  }

  return (
    <div className="container">
      <div className="card">
        <h1>VortexTechPortal — Schools</h1>
        {error && <p style={{ color: 'red' }}>{error}</p>}
        <h2>Create school</h2>
        <form onSubmit={createSchool} style={{ display: 'grid', gap: '.5rem', marginBottom: '1.5rem' }}>
          <input placeholder="School code" value={schoolForm.code} onChange={(e) => setSchoolForm({ ...schoolForm, code: e.target.value })} />
          <input placeholder="School name" value={schoolForm.name} onChange={(e) => setSchoolForm({ ...schoolForm, name: e.target.value })} />
          <input placeholder="Province" value={schoolForm.province} onChange={(e) => setSchoolForm({ ...schoolForm, province: e.target.value })} />
          <button type="submit" disabled={creatingSchool}>{creatingSchool ? 'Creating...' : 'Create school'}</button>
        </form>

        <h2>Create school admin</h2>
        {adminMsg && <p style={{ color: 'green' }}>{adminMsg}</p>}
        <form onSubmit={createAdmin} style={{ display: 'grid', gap: '.5rem', marginBottom: '1.5rem' }}>
          <select value={adminForm.school_id} onChange={(e) => setAdminForm({ ...adminForm, school_id: e.target.value })}>
            {schools.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
          </select>
          <input placeholder="Admin full name" value={adminForm.full_name} onChange={(e) => setAdminForm({ ...adminForm, full_name: e.target.value })} />
          <input type="email" placeholder="Admin email" value={adminForm.email} onChange={(e) => setAdminForm({ ...adminForm, email: e.target.value })} />
          <input type="password" placeholder="Admin password" value={adminForm.password} onChange={(e) => setAdminForm({ ...adminForm, password: e.target.value })} />
          <select value={adminForm.role} onChange={(e) => setAdminForm({ ...adminForm, role: e.target.value })}>
            <option value="owner">Owner</option>
            <option value="bursar">Bursar</option>
            <option value="headmaster">Headmaster</option>
            <option value="teacher">Teacher</option>
          </select>
          <button type="submit" disabled={creatingAdmin}>{creatingAdmin ? 'Creating...' : 'Create admin'}</button>
        </form>

        <h2>Schools</h2>
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
