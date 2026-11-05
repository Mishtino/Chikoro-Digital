import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function SchoolStaffDirectory() {
  const router = useRouter();
  const [staff, setStaff] = useState([]);
  const [schoolName, setSchoolName] = useState('');
  const [role, setRole] = useState('');
  const [query, setQuery] = useState('');
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
        if (!['owner', 'headmaster'].includes(profile.role) || profile.is_admin) {
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

  const visibleStaff = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return staff;
    return staff.filter(member =>
      [member.full_name, member.email, member.role, member.is_active ? 'active' : 'disabled']
        .some(value => String(value || '').toLowerCase().includes(term))
    );
  }, [staff, query]);

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  return (
    <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '32px 18px', color: '#172033' }}>
      <section style={{ maxWidth: 1040, margin: '0 auto' }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 28 }}>
          <div><p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>CHIKORO DIGITAL · SCHOOL ADMINISTRATION</p><h1 style={{ margin: '8px 0 4px' }}>Staff directory</h1><p style={{ margin: 0, color: '#53627a' }}>{schoolName || 'Your school'} · Signed in as {role.replaceAll('_', ' ')}</p></div>
          <button type="button" onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff', padding: '10px 14px', cursor: 'pointer' }}>Sign out</button>
        </header>
        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22, boxShadow: '0 8px 28px rgba(15,23,42,.04)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 18 }}>
            <div><h2 style={{ margin: 0 }}>School staff</h2><p style={{ color: '#64748b', margin: '5px 0 0' }}>A school-scoped view of authorised staff accounts.</p></div>
            <strong>{staff.length} accounts</strong>
          </div>
          <label htmlFor="staff-search" style={{ display: 'block', fontWeight: 600, marginBottom: 7 }}>Search staff</label>
          <input id="staff-search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search by name, email, role or status" style={{ width: '100%', maxWidth: 440, padding: 11, border: '1px solid #cbd5e1', borderRadius: 8, marginBottom: 18 }} />
          {error && <p role="alert" style={{ color: '#b42318' }}>{error}</p>}
          {loading ? <p role="status">Loading staff directory…</p> : !error && visibleStaff.length === 0 ? <p>No staff accounts match this search.</p> : !error && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead><tr>{['Name', 'Email', 'Role', 'Account status'].map(label => <th key={label} style={{ padding: 12, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12, textTransform: 'uppercase' }}>{label}</th>)}</tr></thead>
                <tbody>{visibleStaff.map(member => <tr key={member.id}>
                  <td style={{ padding: 12, borderBottom: '1px solid #edf1f5', fontWeight: 600 }}>{member.full_name}</td>
                  <td style={{ padding: 12, borderBottom: '1px solid #edf1f5' }}>{member.email}</td>
                  <td style={{ padding: 12, borderBottom: '1px solid #edf1f5', textTransform: 'capitalize' }}>{member.role.replaceAll('_', ' ')}</td>
                  <td style={{ padding: 12, borderBottom: '1px solid #edf1f5' }}><span style={{ color: member.is_active ? '#067647' : '#b42318', fontWeight: 600 }}>{member.is_active ? 'Active' : 'Disabled'}</span></td>
                </tr>)}</tbody>
              </table>
            </div>
          )}
        </section>
        <p style={{ color: '#64748b', fontSize: 13, marginTop: 16 }}>Staff access changes and invitations are not available here yet. Account provisioning remains controlled through the verified school onboarding workflow.</p>
      </section>
    </main>
  );
}
