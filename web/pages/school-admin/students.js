import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { api } from '../../lib/api';
import Brand from '../../components/Brand';
import { getSupabaseBrowserClient } from '../../lib/supabase';

const emptyForm = { first_name: '', last_name: '', form: '', guardian_name: '', guardian_phone: '', guardian_email: '', student_email: '' };

export default function SchoolStudents() {
  const router = useRouter();
  const [students, setStudents] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState(null);
  const [editForm, setEditForm] = useState({ first_name: '', last_name: '', form: '' });
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [issuedPin, setIssuedPin] = useState(null);

  async function loadStudents() {
    const data = await api('/students');
    setStudents(Array.isArray(data) ? data : []);
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError || !data.session?.access_token) { router.replace('/portal/login'); return; }
        const profile = await api('/auth/supabase/me');
        if (!['owner', 'headmaster'].includes(profile.role) || profile.is_admin || !profile.school_id) {
          await supabase.auth.signOut();
          router.replace('/portal/login');
          return;
        }
        const records = await api('/students');
        if (active) setStudents(Array.isArray(records) ? records : []);
      } catch (e) {
        if (active) setError(e.message || 'Unable to load learners.');
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, [router]);

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    return students.filter(student => {
      const matches = !term || [student.first_name, student.last_name, student.student_number, student.form]
        .some(value => String(value || '').toLowerCase().includes(term));
      const status = statusFilter === 'all' || (statusFilter === 'active' ? student.status === 'active' : student.status !== 'active');
      return matches && status;
    });
  }, [students, query, statusFilter]);

  async function createStudent(event) {
    event.preventDefault();
    setSaving(true); setError(''); setNotice(''); setIssuedPin(null);
    try {
      const payload = { ...form, form: form.form || null };
      Object.keys(payload).forEach(key => { if (typeof payload[key] === 'string') payload[key] = payload[key].trim() || null; });
      payload.first_name = form.first_name.trim();
      payload.last_name = form.last_name.trim();
      const result = await api('/students', { method: 'POST', body: JSON.stringify(payload) });
      setForm(emptyForm);
      await loadStudents();
      if (result.portal_email && result.pin) {
        setIssuedPin({ name: `${result.first_name} ${result.last_name}`, number: result.student_number, pin: result.pin });
        setNotice('Learner created. Share the activation PIN securely with the learner or guardian.');
      } else {
        setNotice(`Learner ${result.student_number} created successfully.`);
      }
    } catch (e) { setError(e.message || 'Learner could not be created.'); }
    finally { setSaving(false); }
  }

  function beginEdit(student) {
    setEditing(student.id);
    setEditForm({ first_name: student.first_name, last_name: student.last_name, form: student.form || '' });
    setError(''); setNotice(''); setIssuedPin(null);
  }

  async function saveEdit(event) {
    event.preventDefault();
    setBusyId(editing); setError(''); setNotice('');
    try {
      await api(`/students/${editing}`, {
        method: 'PATCH',
        body: JSON.stringify({ first_name: editForm.first_name.trim(), last_name: editForm.last_name.trim(), form: editForm.form.trim() || null }),
      });
      setStudents(current => current.map(item => item.id === editing ? { ...item, ...editForm, form: editForm.form.trim() || null } : item));
      setEditing(null);
      setNotice('Learner record updated.');
    } catch (e) { setError(e.message || 'Learner record could not be updated.'); }
    finally { setBusyId(null); }
  }

  async function issuePin(student) {
    setBusyId(student.id); setError(''); setNotice(''); setIssuedPin(null);
    try {
      const result = await api(`/students/${student.id}/activation-pin`, { method: 'POST' });
      setIssuedPin({ name: `${student.first_name} ${student.last_name}`, number: student.student_number, pin: result.activation_pin, expires: result.expires_at });
      setNotice('A new activation PIN has been issued. Share it securely; it will not be shown again.');
    } catch (e) { setError(e.message || 'An activation PIN could not be issued.'); }
    finally { setBusyId(null); }
  }

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  return <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '30px 18px', color: '#172033' }}>
    <div style={{ maxWidth: 1120, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 14, marginBottom: 24 }}>
        <div><div style={{ marginBottom: 10 }}><Brand compact /></div><p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>SCHOOL WORKSPACE</p><h1 style={{ margin: '7px 0 4px' }}>Learner records</h1><p style={{ margin: 0, color: '#64748b' }}>Register learners and manage their school records.</p></div>
        <div style={{ display: 'flex', gap: 10 }}><Link href="/school-admin" style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 13px', textDecoration: 'none', color: '#172033', background: '#fff' }}>Dashboard</Link><button onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 13px', background: '#fff', cursor: 'pointer' }}>Sign out</button></div>
      </header>

      {error && <p role="alert" style={{ padding: 12, background: '#fff1f0', color: '#b42318', borderRadius: 8 }}>{error}</p>}
      {notice && <p role="status" style={{ padding: 12, background: '#ecfdf3', color: '#067647', borderRadius: 8 }}>{notice}</p>}
      {issuedPin && <section style={{ border: '1px solid #f5cf75', background: '#fffaeb', borderRadius: 12, padding: 18, marginBottom: 18 }}>
        <strong>One-time activation details</strong>
        <p style={{ margin: '8px 0 4px' }}>{issuedPin.name} · {issuedPin.number}</p>
        <p style={{ fontSize: 25, letterSpacing: '.15em', fontWeight: 700, margin: '6px 0' }}>{issuedPin.pin}</p>
        {issuedPin.expires && <p style={{ margin: 0, color: '#7a5a13', fontSize: 13 }}>Expires: {new Date(issuedPin.expires).toLocaleString()}</p>}
        <p style={{ margin: '8px 0 0', color: '#7a5a13', fontSize: 13 }}>Copy or securely deliver this PIN now. It is not stored in this page after you leave.</p>
      </section>}

      <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22, marginBottom: 18 }}>
        <h2 style={{ margin: '0 0 16px', fontSize: 19 }}>Register a learner</h2>
        <form onSubmit={createStudent} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 12 }}>
          {[
            ['first_name', 'First name', true], ['last_name', 'Last name', true], ['form', 'Class / form', false],
            ['student_email', 'Learner portal email', false], ['guardian_name', 'Parent / guardian name', false],
            ['guardian_phone', 'Parent / guardian phone', false], ['guardian_email', 'Parent / guardian email', false],
          ].map(([key, label, required]) => <div key={key}>
            <label htmlFor={key} style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 6 }}>{label}</label>
            <input id={key} type={key.endsWith('email') ? 'email' : 'text'} required={required} maxLength={key === 'student_email' || key === 'guardian_email' ? 255 : 120} value={form[key]} onChange={e => setForm(current => ({ ...current, [key]: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', border: '1px solid #cbd5e1', borderRadius: 8, padding: 10 }} />
          </div>)}
          <div style={{ display: 'flex', alignItems: 'end' }}><button disabled={saving} type="submit" style={{ width: '100%', border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: 12, fontWeight: 600, cursor: saving ? 'wait' : 'pointer' }}>{saving ? 'Registering…' : 'Register learner'}</button></div>
        </form>
        <p style={{ color: '#64748b', fontSize: 12, margin: '12px 0 0' }}>A portal email is optional. Learners without one can be added now and linked to a portal account later.</p>
      </section>

      <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
          <div><h2 style={{ margin: 0, fontSize: 19 }}>Learners</h2><p style={{ color: '#64748b', margin: '5px 0 0' }}>{visible.length} of {students.length} records</p></div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input aria-label="Search learners" placeholder="Search name, number or form" value={query} onChange={e => setQuery(e.target.value)} style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: 9, minWidth: 220 }} />
            <select aria-label="Filter learner status" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: 9, background: '#fff' }}><option value="all">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select>
          </div>
        </div>
        {loading ? <p role="status">Loading learner records…</p> : students.length === 0 ? <p>No learners registered yet.</p> : visible.length === 0 ? <p>No learners match your search.</p> : <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: 700 }}>
            <thead><tr>{['Student number', 'Learner', 'Form', 'Status', 'Portal', 'Actions'].map(item => <th key={item} style={{ padding: 11, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12, textTransform: 'uppercase' }}>{item}</th>)}</tr></thead>
            <tbody>{visible.map(student => <tr key={student.id}>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5', fontWeight: 600 }}>{student.student_number}</td>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{student.first_name} {student.last_name}</td>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{student.form || '—'}</td>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{student.status}</td>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{!student.portal_enabled ? 'Not enabled' : student.activated ? 'Activated' : 'Pending activation'}</td>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>
                <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
                  <button type="button" onClick={() => beginEdit(student)} style={{ border: '1px solid #cbd5e1', background: '#fff', borderRadius: 7, padding: '6px 9px', cursor: 'pointer' }}>Edit</button>
                  {!student.activated && student.portal_enabled && <button type="button" disabled={busyId === student.id} onClick={() => issuePin(student)} style={{ border: '1px solid #cbd5e1', background: '#fff', borderRadius: 7, padding: '6px 9px', cursor: 'pointer' }}>Issue PIN</button>}
                </div>
              </td>
            </tr>)}</tbody>
          </table>
        </div>}
      </section>

      {editing !== null && <div role="dialog" aria-modal="true" aria-labelledby="edit-title" style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,.45)', display: 'grid', placeItems: 'center', padding: 18, zIndex: 20 }}>
        <form onSubmit={saveEdit} style={{ background: '#fff', borderRadius: 14, padding: 22, width: 'min(100%, 460px)', boxSizing: 'border-box' }}>
          <h2 id="edit-title" style={{ marginTop: 0 }}>Edit learner record</h2>
          {['first_name', 'last_name', 'form'].map(key => <div key={key} style={{ marginBottom: 12 }}><label htmlFor={`edit-${key}`} style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>{key.replace('_', ' ')}</label><input id={`edit-${key}`} required={key !== 'form'} value={editForm[key]} onChange={e => setEditForm(current => ({ ...current, [key]: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>)}
          <div style={{ display: 'flex', justifyContent: 'end', gap: 8 }}><button type="button" onClick={() => setEditing(null)} style={{ padding: '9px 12px', border: '1px solid #cbd5e1', background: '#fff', borderRadius: 8 }}>Cancel</button><button type="submit" disabled={busyId === editing} style={{ padding: '9px 12px', border: 0, background: '#2457c5', color: '#fff', borderRadius: 8 }}>Save changes</button></div>
        </form>
      </div>}
    </div>
  </main>;
}
