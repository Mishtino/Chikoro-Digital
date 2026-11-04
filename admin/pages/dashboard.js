import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseBrowserClient } from '../lib/supabase';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Dashboard() {
  const router = useRouter();
  const [schools, setSchools] = useState([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [schoolForm, setSchoolForm] = useState({ code: '', name: '', province: '' });
  const [creatingSchool, setCreatingSchool] = useState(false);
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditLoading, setAuditLoading] = useState(false);
  const [platformAccess, setPlatformAccess] = useState({ role: '', permissions: [] });
  const can = (permission) => platformAccess.permissions.includes(permission);

  async function getAdminToken() {
    const supabase = getSupabaseBrowserClient();
    const { data, error } = await supabase.auth.getSession();
    if (error || !data.session?.access_token) {
      router.replace('/');
      return null;
    }
    const token = data.session.access_token;
    const identity = await fetch(`${API}/platform/access/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const profile = await identity.json().catch(() => ({}));
    if (!identity.ok || !profile.is_platform_staff) {
      await supabase.auth.signOut();
      router.replace('/');
      throw new Error('This account is not authorised for the Vortex Developer Portal.');
    }
    setPlatformAccess({ role: profile.role || '', permissions: profile.permissions || [] });
    return { token, profile };
  }

  async function load() {
    setLoading(true);
    try {
      const auth = await getAdminToken();
      if (!auth) return;
      const { token, profile } = auth;
      const permissions = profile.permissions || [];
      if (permissions.includes('schools:read')) {
        const res = await fetch(`${API}/schools`, { headers: { Authorization: `Bearer ${token}` } });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load schools');
        setSchools(Array.isArray(data) ? data : []);
      } else {
        setSchools([]);
      }
      if (permissions.includes('audit:read')) {
        const auditRes = await fetch(`${API}/platform/audit-logs?limit=8&offset=0`, { headers: { Authorization: `Bearer ${token}` } });
        if (auditRes.ok) {
          const auditData = await auditRes.json();
          setAuditLogs(Array.isArray(auditData.items) ? auditData.items : []);
          setAuditTotal(Number(auditData.total || 0));
        }
      } else {
        setAuditLogs([]);
        setAuditTotal(0);
      }
      setError('');
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function createSchool(e) {
    e.preventDefault();
    setCreatingSchool(true); setError(''); setNotice('');
    try {
      const auth = await getAdminToken();
      if (!auth) return;
      const token = auth.token;
      const res = await fetch(`${API}/schools`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(schoolForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'School creation failed');
      setSchoolForm({ code: '', name: '', province: '' });
      setNotice(`${data.name} has been added to Chikoro Digital.`);
      await load();
    } catch (e) { setError(e.message); }
    finally { setCreatingSchool(false); }
  }

  const visibleSchools = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return schools;
    return schools.filter((school) =>
      [school.code, school.name, school.province, school.status, school.plan]
        .some((value) => String(value || '').toLowerCase().includes(term))
    );
  }, [schools, query]);

  async function updateSchoolStatus(school, nextStatus) {
    const action = nextStatus === 'suspended' ? 'suspend' : nextStatus === 'live' ? 'activate' : 'return to onboarding';
    if (!window.confirm(`Are you sure you want to ${action} ${school.name}?`)) return;
    setError(''); setNotice('');
    try {
      const auth = await getAdminToken();
      if (!auth) return;
      const token = auth.token;
      const res = await fetch(`${API}/schools/${school.id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ status: nextStatus, reason: 'Changed from Vortex Developer Portal' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'School status update failed');
      setNotice(`${school.name} status changed to ${data.status}.`);
      await load();
    } catch (e) { setError(e.message); }
  }

  async function logout() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/');
  }

  return (
    <main className="admin-dashboard">
      <header className="dashboard-topbar">
        <a className="dashboard-brand" href="/dashboard"><span className="admin-mark">V</span><span><strong>VORTEX TECHNOLOGIES</strong><small>VORTEX DEVELOPER PORTAL</small></span></a>
        <button className="dashboard-logout" type="button" onClick={logout}>Sign out</button>
      </header>

      <div className="dashboard-content">
        <div className="dashboard-heading">
          <div><span className="admin-eyebrow">Vortex Technologies · Platform operations</span><h1>Developer control centre</h1><p>Signed in with <strong>{platformAccess.role.replaceAll('_', ' ')}</strong> access. Available controls depend on your assigned permissions.</p></div>
          <span className="dashboard-secure"><span /> Secure platform access</span>
        </div>

        {error && <div className="admin-alert error" role="alert">{error}</div>}
        {notice && <div className="admin-alert success" role="status">{notice}</div>}

        {can('schools:read') && <section className="dashboard-stats" aria-label="School statistics">
          <article className="dashboard-stat"><span>Total schools</span><strong>{schools.length}</strong><small>Registered on the platform</small></article>
          <article className="dashboard-stat"><span>Live schools</span><strong>{schools.filter(s => s.status === 'live').length}</strong><small>Currently operational</small></article>
          <article className="dashboard-stat"><span>Onboarding</span><strong>{schools.filter(s => s.status === 'onboarding').length}</strong><small>Setup in progress</small></article>
        </section>}

        <div className="dashboard-grid">
          {can('schools:write') && <section className="dashboard-card create-school-card">
            <div className="dashboard-card-heading"><div><span className="admin-eyebrow">New institution</span><h2>Add a school</h2></div><span className="dashboard-plus">+</span></div>
            <p className="dashboard-description">Register a school before setting up its staff, learners and parent accounts.</p>
            <form onSubmit={createSchool}>
              <label htmlFor="school-code">School code</label>
              <input id="school-code" value={schoolForm.code} onChange={e => setSchoolForm({ ...schoolForm, code: e.target.value })} placeholder="e.g. CHI001" minLength={2} maxLength={20} required />
              <label htmlFor="school-name">School name</label>
              <input id="school-name" value={schoolForm.name} onChange={e => setSchoolForm({ ...schoolForm, name: e.target.value })} placeholder="Enter registered school name" minLength={2} maxLength={200} required />
              <label htmlFor="school-province">Province <span className="optional-label">Optional</span></label>
              <input id="school-province" value={schoolForm.province} onChange={e => setSchoolForm({ ...schoolForm, province: e.target.value })} placeholder="e.g. Harare" maxLength={100} />
              <button className="admin-button" type="submit" disabled={creatingSchool}>{creatingSchool ? 'Adding school…' : 'Add school'}</button>
            </form>
          </section>}

          {can('schools:read') && <section className="dashboard-card school-list-card">
            <div className="school-list-heading"><div><span className="admin-eyebrow">Institution directory</span><h2>Registered schools</h2></div><span className="school-count">{schools.length} total</span></div>
            <div className="school-search"><input aria-label="Search schools" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search by name, code or province…" /><span>⌕</span></div>
            {loading ? <div className="dashboard-empty">Loading school directory…</div> :
              visibleSchools.length === 0 ? <div className="dashboard-empty">{schools.length ? 'No schools match your search.' : 'No schools have been registered yet. Add your first school to get started.'}</div> :
              <div className="school-table-wrap"><table className="school-table">
                <thead><tr><th>School</th><th>Province</th><th>Status</th><th>Plan</th>{can('schools:lifecycle') && <th>Actions</th>}</tr></thead>
                <tbody>{visibleSchools.map(school => <tr key={school.id}><td><strong>{school.name}</strong><small>{school.code}</small></td><td>{school.province || '—'}</td><td><span className={`school-status status-${school.status}`}>{school.status}</span></td><td>{school.plan || '—'}</td>{can('schools:lifecycle') && <td className="school-actions">{school.status === 'suspended' ? <button type="button" onClick={() => updateSchoolStatus(school, 'onboarding')}>Reinstate</button> : <><button type="button" onClick={() => updateSchoolStatus(school, 'live')} disabled={school.status === 'live'}>Set live</button><button type="button" onClick={() => updateSchoolStatus(school, 'suspended')}>Suspend</button></>}</td>}</tr>)}</tbody>
              </table></div>
            }
            <button className="dashboard-refresh" type="button" onClick={load} disabled={loading}>↻ Refresh directory</button>
          </section>}
        </div>
        {can('audit:read') && <section className="dashboard-card platform-audit-card">
          <div className="school-list-heading"><div><span className="admin-eyebrow">Security and accountability</span><h2>Recent platform activity</h2></div><span className="school-count">{auditTotal} events</span></div>
          <p className="dashboard-description">Latest platform-wide actions recorded for operational review.</p>
          {auditLogs.length === 0 ? <div className="dashboard-empty">No platform activity has been recorded yet.</div> : (
            <div className="audit-list">
              {auditLogs.map((item) => (
                <article className="audit-row" key={item.id}>
                  <div className="audit-event"><strong>{item.action.replaceAll(".", " ")}</strong><small>{item.entity_type || "system"}{item.entity_id ? " · #" + item.entity_id : ""}</small></div>
                  <div className="audit-actor"><strong>{item.actor_name || item.actor_email || "System"}</strong><small>{item.actor_email || "Automated event"}</small></div>
                  <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time>
                </article>
              ))}
            </div>
          )}
          <button className="dashboard-refresh" type="button" onClick={load} disabled={loading || auditLoading}>↻ Refresh activity</button>
        </section>}
        <footer className="dashboard-footer">Chikoro Digital · Vortex Technologies <span>Vortex platform operations</span></footer>
      </div>
    </main>
  );
}
