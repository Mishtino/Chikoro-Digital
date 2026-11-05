import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

const STAFF_ROLES = ['owner', 'headmaster', 'bursar', 'teacher'];

function roleLabel(role) {
  return String(role || 'unknown').replaceAll('_', ' ');
}

export default function SchoolStaffDirectory() {
  const router = useRouter();
  const [staff, setStaff] = useState([]);
  const [schoolName, setSchoolName] = useState('');
  const [role, setRole] = useState('');
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError || !data.session?.access_token) {
          router.replace('/portal/login');
          return;
        }
        const profile = await api('/auth/supabase/me');
        if (!['owner', 'headmaster'].includes(profile.role) || profile.is_admin || !profile.school_id) {
          await supabase.auth.signOut();
          router.replace('/portal/login');
          return;
        }
        const directory = await api('/users');
        if (!active) return;
        setRole(profile.role);
        setSchoolName(profile.school_name || '');
        setStaff(Array.isArray(directory) ? directory : []);
      } catch (e) {
        if (active) setError(e.message || 'Unable to load the staff directory.');
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, [router]);

  const counts = useMemo(() => ({
    total: staff.length,
    active: staff.filter(member => member.is_active).length,
    disabled: staff.filter(member => !member.is_active).length,
  }), [staff]);

  const visibleStaff = useMemo(() => {
    const term = query.trim().toLowerCase();
    return staff.filter(member => {
      const matchesQuery = !term || [
        member.full_name, member.email, member.role, member.is_active ? 'active' : 'disabled',
      ].some(value => String(value || '').toLowerCase().includes(term));
      const matchesRole = roleFilter === 'all' || member.role === roleFilter;
      const matchesStatus = statusFilter === 'all'
        || (statusFilter === 'active' ? member.is_active : !member.is_active);
      return matchesQuery && matchesRole && matchesStatus;
    });
  }, [staff, query, roleFilter, statusFilter]);

  function clearFilters() {
    setQuery('');
    setRoleFilter('all');
    setStatusFilter('all');
  }

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  return (
    <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '32px 18px', color: '#172033' }}>
      <section style={{ maxWidth: 1040, margin: '0 auto' }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 28 }}>
          <div><p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>CHIKORO DIGITAL · SCHOOL ADMINISTRATION</p><h1 style={{ margin: '8px 0 4px' }}>Staff directory</h1><p style={{ margin: 0, color: '#53627a' }}>{schoolName || 'Your school'} · Signed in as {roleLabel(role)}</p></div>
          <button type="button" onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff', padding: '10px 14px', cursor: 'pointer' }}>Sign out</button>
        </header>
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 18 }}>
          {[['Total staff', counts.total], ['Active accounts', counts.active], ['Disabled accounts', counts.disabled]].map(([label, value]) => (
            <article key={label} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 16 }}>
              <p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>{label}</p><strong style={{ display: 'block', marginTop: 6, fontSize: 25 }}>{value}</strong>
            </article>
          ))}
        </section>
        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22, boxShadow: '0 8px 28px rgba(15,23,42,.04)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 18 }}>
            <div><h2 style={{ margin: 0 }}>School staff</h2><p style={{ color: '#64748b', margin: '5px 0 0' }}>A school-scoped view of authorised staff accounts.</p></div>
            <strong>{visibleStaff.length} of {staff.length} shown</strong>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12, marginBottom: 18 }}>
            <div><label htmlFor="staff-search" style={{ display: 'block', fontWeight: 600, marginBottom: 7 }}>Search staff</label><input id="staff-search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Name, email, role or status" style={{ boxSizing: 'border-box', width: '100%', padding: 11, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <div><label htmlFor="staff-role" style={{ display: 'block', fontWeight: 600, marginBottom: 7 }}>Filter by role</label><select id="staff-role" value={roleFilter} onChange={e => setRoleFilter(e.target.value)} style={{ boxSizing: 'border-box', width: '100%', padding: 11, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}><option value="all">All roles</option>{STAFF_ROLES.map(item => <option key={item} value={item}>{roleLabel(item)}</option>)}</select></div>
            <div><label htmlFor="staff-status" style={{ display: 'block', fontWeight: 600, marginBottom: 7 }}>Filter by status</label><select id="staff-status" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ boxSizing: 'border-box', width: '100%', padding: 11, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}><option value="all">All statuses</option><option value="active">Active</option><option value="disabled">Disabled</option></select></div>
          </div>
          {(query || roleFilter !== 'all' || statusFilter !== 'all') && <button type="button" onClick={clearFilters} style={{ border: 0, background: 'transparent', color: '#2457c5', padding: '0 0 14px', cursor: 'pointer', fontWeight: 600 }}>Clear filters</button>}
          {error && <p role="alert" style={{ color: '#b42318' }}>{error}</p>}
          {loading ? <p role="status">Loading staff directory…</p> : !error && visibleStaff.length === 0 ? <p>No staff accounts match these filters.</p> : !error && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead><tr>{['Name', 'Email', 'Role', 'Account status'].map(label => <th key={label} scope="col" style={{ padding: 12, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12, textTransform: 'uppercase' }}>{label}</th>)}</tr></thead>
                <tbody>{visibleStaff.map(member => <tr key={member.id}>
                  <td style={{ padding: 12, borderBottom: '1px solid #edf1f5', fontWeight: 600 }}>{member.full_name}</td>
                  <td style={{ padding: 12, borderBottom: '1px solid #edf1f5' }}>{member.email}</td>
                  <td style={{ padding: 12, borderBottom: '1px solid #edf1f5', textTransform: 'capitalize' }}>{roleLabel(member.role)}</td>
                  <td style={{ padding: 12, borderBottom: '1px solid #edf1f5' }}><span style={{ color: member.is_active ? '#067647' : '#b42318', fontWeight: 600 }}>{member.is_active ? 'Active' : 'Disabled'}</span></td>
                </tr>)}</tbody>
              </table>
            </div>
          )}
        </section>
        <p style={{ color: '#64748b', fontSize: 13, marginTop: 16 }}>Staff invitations and account changes are not enabled yet. Provisioning remains gated until school onboarding and Supabase Auth prerequisites are verified.</p>
      </section>
    </main>
  );
}
