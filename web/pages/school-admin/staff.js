import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

const STAFF_ROLES = ['owner', 'headmaster', 'bursar', 'teacher'];
const DEFAULT_CAPABILITIES = {
  invitations_enabled: false,
  lifecycle_enabled: false,
  invitable_roles: [],
  manageable_roles: [],
};

function roleLabel(role) {
  return String(role || 'unknown').replaceAll('_', ' ');
}

export default function SchoolStaffDirectory() {
  const router = useRouter();
  const [staff, setStaff] = useState([]);
  const [schoolName, setSchoolName] = useState('');
  const [role, setRole] = useState('');
  const [profileId, setProfileId] = useState(null);
  const [capabilities, setCapabilities] = useState(DEFAULT_CAPABILITIES);
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteRole, setInviteRole] = useState('teacher');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [busyUserId, setBusyUserId] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function refreshDirectory() {
    const directory = await api('/users');
    setStaff(Array.isArray(directory) ? directory : []);
  }

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
        let readiness = DEFAULT_CAPABILITIES;
        try {
          readiness = await api('/users/staff-management/capabilities');
        } catch {
          // Fail closed in the UI if the API readiness endpoint is unavailable.
        }
        if (!active) return;
        setRole(profile.role);
        setProfileId(profile.id);
        setSchoolName(profile.school_name || '');
        setStaff(Array.isArray(directory) ? directory : []);
        setCapabilities(readiness || DEFAULT_CAPABILITIES);
        setInviteRole(readiness?.invitable_roles?.[0] || 'teacher');
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

  async function submitInvitation(event) {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    setNotice('');
    try {
      const result = await api('/users/invitations', {
        method: 'POST',
        body: JSON.stringify({ email: inviteEmail, full_name: inviteName, role: inviteRole }),
      });
      setNotice(result.message || 'Invitation sent.');
      setInviteEmail('');
      setInviteName('');
      await refreshDirectory();
    } catch (e) {
      setError(e.message || 'The staff invitation could not be sent.');
    } finally {
      setSubmitting(false);
    }
  }

  async function changeRole(member, nextRole) {
    if (!nextRole || nextRole === member.role) return;
    setBusyUserId(member.id);
    setError('');
    setNotice('');
    try {
      await api(`/users/${member.id}/role`, {
        method: 'PATCH',
        body: JSON.stringify({ role: nextRole }),
      });
      setStaff(current => current.map(item => item.id === member.id ? { ...item, role: nextRole } : item));
      setNotice(`${member.full_name}'s role was updated.`);
    } catch (e) {
      setError(e.message || 'The staff role could not be changed.');
    } finally {
      setBusyUserId(null);
    }
  }

  async function changeStatus(member) {
    const nextActive = !member.is_active;
    setBusyUserId(member.id);
    setError('');
    setNotice('');
    try {
      await api(`/users/${member.id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: nextActive }),
      });
      setStaff(current => current.map(item => item.id === member.id ? { ...item, is_active: nextActive } : item));
      setNotice(nextActive ? `${member.full_name}'s account was reactivated.` : `${member.full_name}'s account was disabled.`);
    } catch (e) {
      setError(e.message || 'The staff account status could not be changed.');
    } finally {
      setBusyUserId(null);
    }
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
        {capabilities.invitations_enabled ? (
          <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22, marginBottom: 18 }}>
            <h2 style={{ margin: 0 }}>Invite staff member</h2>
            <p style={{ color: '#64748b', margin: '5px 0 16px' }}>The new account stays inactive until the invitee verifies their email and activates access.</p>
            <form onSubmit={submitInvitation} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, alignItems: 'end' }}>
              <div><label htmlFor="invite-name" style={{ display: 'block', fontWeight: 600, marginBottom: 7 }}>Full name</label><input id="invite-name" required maxLength={200} value={inviteName} onChange={e => setInviteName(e.target.value)} style={{ boxSizing: 'border-box', width: '100%', padding: 11, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
              <div><label htmlFor="invite-email" style={{ display: 'block', fontWeight: 600, marginBottom: 7 }}>Email address</label><input id="invite-email" type="email" required maxLength={255} value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} style={{ boxSizing: 'border-box', width: '100%', padding: 11, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
              <div><label htmlFor="invite-role" style={{ display: 'block', fontWeight: 600, marginBottom: 7 }}>Staff role</label><select id="invite-role" value={inviteRole} onChange={e => setInviteRole(e.target.value)} style={{ boxSizing: 'border-box', width: '100%', padding: 11, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}>{capabilities.invitable_roles.map(item => <option key={item} value={item}>{roleLabel(item)}</option>)}</select></div>
              <button type="submit" disabled={submitting} style={{ border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: '12px 16px', cursor: submitting ? 'wait' : 'pointer', opacity: submitting ? .7 : 1 }}>{submitting ? 'Sending…' : 'Send invitation'}</button>
            </form>
          </section>
        ) : (
          <p style={{ color: '#64748b', fontSize: 13, margin: '0 0 18px' }}>Staff invitations are currently disabled until the school, database and Supabase Auth release checks are complete.</p>
        )}
        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22, boxShadow: '0 8px 28px rgba(15,23,42,.04)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 18 }}>
            <div><h2 style={{ margin: 0 }}>School staff</h2><p style={{ color: '#64748b', margin: '5px 0 0' }}>A school-scoped view of authorised staff accounts.</p></div>
            <strong>{visibleStaff.length} of {staff.length} shown</strong>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12, marginBottom: 18 }}>
            <div><label htmlFor="staff-search" style={{ display: 'block', fontWeight: 600, marginBottom: 7 }}>Search staff</label><input id="staff-search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Name, email, role or status" style={{ boxSizing: 'border-box', width: '100%', padding: 11, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <div><label htmlFor="staff-role" style={{ display: 'block', fontWeight: 600, marginBottom: 7 }}>Filter by role</label><select id="staff-role" value={roleFilter} onChange={e => setRoleFilter(e.target.value)} style={{ boxSizing: 'border-box', width: '100%', padding: 11, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}><option value="all">All roles</option>{STAFF_ROLES.map(item => <option key={item} value={item}>{roleLabel(item)}</option>)}</select></div>
            <div><label htmlFor="staff-status" style={{ display: 'block', fontWeight: 600, marginBottom: 7 }}>Filter by status</label><select id="staff-status" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ boxSizing: 'border-box', width: '100%', padding: 11, border: '1px solid #cbd5e1', borderRadius: 8, borderRadius: 8, background: '#fff' }}><option value="all">All statuses</option><option value="active">Active</option><option value="disabled">Disabled</option></select></div>
          </div>
          {(query || roleFilter !== 'all' || statusFilter !== 'all') && <button type="button" onClick={clearFilters} style={{ border: 0, background: 'transparent', color: '#2457c5', padding: '0 0 14px', cursor: 'pointer', fontWeight: 600 }}>Clear filters</button>}
          {error && <p role="alert" style={{ color: '#b42318' }}>{error}</p>}
          {notice && <p role="status" style={{ color: '#067647' }}>{notice}</p>}
          {loading ? <p role="status">Loading staff directory…</p> : !error && visibleStaff.length === 0 ? <p>No staff accounts match these filters.</p> : !error && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead><tr>{['Name', 'Email', 'Role', 'Account status', ...(capabilities.lifecycle_enabled ? ['Actions'] : [])].map(label => <th key={label} scope="col" style={{ padding: 12, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12, textTransform: 'uppercase' }}>{label}</th>)}</tr></thead>
                <tbody>{visibleStaff.map(member => {
                  const canManage = capabilities.lifecycle_enabled
                    && member.id !== profileId
                    && capabilities.manageable_roles.includes(member.role);
                  return <tr key={member.id}>
                    <td style={{ padding: 12, borderBottom: '1px solid #edf1f5', fontWeight: 600 }}>{member.full_name}</td>
                    <td style={{ padding: 12, borderBottom: '1px solid #edf1f5' }}>{member.email}</td>
                    <td style={{ padding: 12, borderBottom: '1px solid #edf1f5', textTransform: 'capitalize' }}>
                      {canManage ? <select aria-label={`Change role for ${member.full_name}`} value={member.role} disabled={busyUserId === member.id} onChange={e => changeRole(member, e.target.value)} style={{ padding: 7, border: '1px solid #cbd5e1', borderRadius: 7, background: '#fff' }}>{[member.role, ...capabilities.manageable_roles.filter(item => item !== member.role)].map(item => <option key={item} value={item}>{roleLabel(item)}</option>)}</select> : roleLabel(member.role)}
                    </td>
                    <td style={{ padding: 12, borderBottom: '1px solid #edf1f5' }}><span style={{ color: member.is_active ? '#067647' : '#b42318', fontWeight: 600 }}>{member.is_active ? 'Active' : 'Disabled'}</span></td>
                    {capabilities.lifecycle_enabled && <td style={{ padding: 12, borderBottom: '1px solid #edf1f5' }}>{canManage ? <button type="button" disabled={busyUserId === member.id} onClick={() => changeStatus(member)} style={{ border: '1px solid #cbd5e1', borderRadius: 7, background: '#fff', padding: '7px 10px', cursor: busyUserId === member.id ? 'wait' : 'pointer' }}>{member.is_active ? 'Disable' : 'Reactivate'}</button> : '—'}</td>}
                  </tr>;
                })}</tbody>
              </table>
            </div>
          )}
        </section>
        {!capabilities.lifecycle_enabled && <p style={{ color: '#64748b', fontSize: 13, marginTop: 16 }}>Role changes and account activation/deactivation remain disabled until the separate staff lifecycle release gate is approved.</p>}
      </section>
    </main>
  );
}
