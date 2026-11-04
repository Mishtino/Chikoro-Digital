import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseBrowserClient } from '../lib/supabase';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Dashboard() {
  const router = useRouter();
  const [schools, setSchools] = useState([]);
  const [error, setError] = useState('');
  const [schoolForm, setSchoolForm] = useState({ code: '', name: '', province: '' });
  const [creatingSchool, setCreatingSchool] = useState(false);
  async function getAdminToken() {
    const supabase = getSupabaseBrowserClient();
    const { data, error } = await supabase.auth.getSession();
    if (error || !data.session?.access_token) {
      router.replace('/');
      return null;
    }
    const token = data.session.access_token;
    const identity = await fetch(`${API}/auth/supabase/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const profile = await identity.json().catch(() => ({}));
    if (!identity.ok || !profile.is_admin) {
      await supabase.auth.signOut();
      router.replace('/');
      throw new Error('This account is not authorised for the Vortex control centre.');
    }
    return token;
  }

  async function load() {
    try {
      const token = await getAdminToken();
      if (!token) return;
      const res = await fetch(`${API}/schools`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load schools');
      setSchools(data);
    } catch (e) { setError(e.message); }
  }

  useEffect(() => { load(); }, [router]);

  async function createSchool(e) {
    e.preventDefault();
    setCreatingSchool(true); setError('');
    try {
      const token = await getAdminToken();
      if (!token) return;
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

        <h2>Staff accounts</h2>
        <p>New staff accounts will be provisioned through verified Supabase invitations. Legacy local-password account creation is disabled to protect account ownership and school access.</p>

        <h2>Schools</h2>
        <table>
          <thead><tr><th>Code</th><th>Name</th><th>Province</th><th>Status</th><th>Plan</th></tr></thead>
          <tbody>
            {schools.map((s) => (
              <tr key={s.id}><td>{s.code}</td><td>{s.name}</td><td>{s.province}</td><td>{s.status}</td><td>{s.plan}</td></tr>
            ))}
          </tbody>
        </table>
        <p style={{ marginTop: '1rem' }}><a href="#" onClick={async (event) => { event.preventDefault(); await getSupabaseBrowserClient().auth.signOut(); router.push('/'); }}>Log out</a></p>
      </div>
    </div>
  );
}
