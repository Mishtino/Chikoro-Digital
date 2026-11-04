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
  const [loading, setLoading] = useState(true);

  async function apiRequest(path, options = {}) {
    const { data: { session } } = await getSupabaseBrowserClient().auth.getSession();
    if (!session) { await router.replace('/'); throw new Error('Your session has expired.'); }
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}), Authorization: `Bearer ${session.access_token}` },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Request failed');
    return data;
  }

  async function load() {
    try {
      const profile = await apiRequest('/auth/me');
      if (!profile.is_admin) { await getSupabaseBrowserClient().auth.signOut(); await router.replace('/'); return; }
      setSchools(await apiRequest('/schools'));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function createSchool(e) {
    e.preventDefault();
    setCreatingSchool(true); setError('');
    try {
      await apiRequest('/schools', { method: 'POST', body: JSON.stringify(schoolForm) });
      setSchoolForm({ code: '', name: '', province: '' });
      await load();
    } catch (e) { setError(e.message); }
    finally { setCreatingSchool(false); }
  }

  async function logout() {
    await getSupabaseBrowserClient().auth.signOut();
    await router.replace('/');
  }

  if (loading) return <main className="container"><section className="card">Loading administration workspace…</section></main>;

  return (
    <main className="container">
      <section className="card">
        <div className="auth-brand"><span className="auth-mark">V</span><span>VORTEX <b>TECHNOLOGIES</b></span></div>
        <p className="eyebrow">PLATFORM ADMINISTRATION</p>
        <h1>School management</h1>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <h2>Register a school</h2>
        <form className="auth-form" onSubmit={createSchool}>
          <label>School code</label><input required value={schoolForm.code} onChange={(e) => setSchoolForm({ ...schoolForm, code: e.target.value })} />
          <label>School name</label><input required value={schoolForm.name} onChange={(e) => setSchoolForm({ ...schoolForm, name: e.target.value })} />
          <label>Province</label><input value={schoolForm.province} onChange={(e) => setSchoolForm({ ...schoolForm, province: e.target.value })} />
          <button className="auth-submit" type="submit" disabled={creatingSchool}>{creatingSchool ? 'Creating…' : 'Create school'}</button>
        </form>
        <h2>Schools</h2>
        <table><thead><tr><th>Code</th><th>Name</th><th>Province</th><th>Status</th><th>Plan</th></tr></thead>
          <tbody>{schools.map((s) => <tr key={s.id}><td>{s.code}</td><td>{s.name}</td><td>{s.province || '—'}</td><td>{s.status}</td><td>{s.plan}</td></tr>)}</tbody>
        </table>
        <p className="auth-foot">Staff and school administrator accounts must be provisioned through the verified Supabase Auth workflow. Direct legacy password creation is disabled.</p>
        <button className="auth-submit" type="button" onClick={logout}>Sign out</button>
      </section>
    </main>
  );
}
