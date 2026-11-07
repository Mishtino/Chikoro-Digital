import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { api } from '../../lib/api';
import Brand from '../../components/Brand';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function ClassManagement() {
  const router = useRouter();
  const [profile, setProfile] = useState(null);
  const [classes, setClasses] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [className, setClassName] = useState('');
  const [teacherId, setTeacherId] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const canManage = ['owner', 'headmaster'].includes(profile?.role);

  async function refresh() {
    const [classRows, assignmentRows] = await Promise.all([api('/classes'), api('/classes/assignments')]);
    setClasses(classRows || []);
    setAssignments(assignmentRows || []);
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError || !data.session?.access_token) { router.replace('/portal/login'); return; }
        const currentProfile = await api('/auth/supabase/me');
        if (!['owner', 'headmaster', 'teacher'].includes(currentProfile.role) || currentProfile.is_admin || !currentProfile.school_id) {
          await supabase.auth.signOut();
          router.replace('/portal/login');
          return;
        }
        const requests = [api('/classes'), api('/classes/assignments')];
        if (['owner', 'headmaster'].includes(currentProfile.role)) requests.push(api('/users'));
        const results = await Promise.all(requests);
        if (!active) return;
        setProfile(currentProfile);
        setClasses(results[0] || []);
        setAssignments(results[1] || []);
        setTeachers((results[2] || []).filter(user => user.role === 'teacher' && user.is_active));
        if (results[0]?.length) setClassName(results[0][0].class_name);
        if (results[2]?.length) {
          const firstTeacher = results[2].find(user => user.role === 'teacher' && user.is_active);
          if (firstTeacher) setTeacherId(String(firstTeacher.id));
        }
      } catch (e) { if (active) setError(e.message || 'Unable to load class assignments.'); }
      finally { if (active) setLoading(false); }
    }
    load();
    return () => { active = false; };
  }, [router]);

  async function assign(event) {
    event.preventDefault(); setSaving(true); setError(''); setNotice('');
    try {
      await api('/classes/assignments', {
        method: 'POST',
        body: JSON.stringify({ class_name: className, teacher_user_id: Number(teacherId) }),
      });
      await refresh();
      setNotice('Teacher assigned to class.');
    } catch (e) { setError(e.message || 'Teacher could not be assigned.'); }
    finally { setSaving(false); }
  }

  async function unassign(id) {
    setSaving(true); setError(''); setNotice('');
    try {
      await api(`/classes/assignments/${id}`, { method: 'DELETE' });
      await refresh();
      setNotice('Teacher assignment removed.');
    } catch (e) { setError(e.message || 'Assignment could not be removed.'); }
    finally { setSaving(false); }
  }

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  return <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '30px 18px', color: '#172033' }}>
    <div style={{ maxWidth: 1050, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 24 }}>
        <div><div style={{ marginBottom: 10 }}><Brand compact /></div><p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>SCHOOL WORKSPACE</p><h1 style={{ margin: '7px 0 4px' }}>Classes & teacher assignments</h1><p style={{ margin: 0, color: '#64748b' }}>Connect teachers to the classes they are responsible for.</p></div>
        <div style={{ display: 'flex', gap: 8 }}><Link href="/school-admin" style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', textDecoration: 'none', color: '#172033', background: '#fff' }}>Dashboard</Link><button onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', background: '#fff', cursor: 'pointer' }}>Sign out</button></div>
      </header>
      {error && <p role="alert" style={{ padding: 12, background: '#fff1f0', color: '#b42318', borderRadius: 8 }}>{error}</p>}
      {notice && <p role="status" style={{ padding: 12, background: '#ecfdf3', color: '#067647', borderRadius: 8 }}>{notice}</p>}
      {loading ? <p role="status">Loading classes…</p> : !error && <>
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12, marginBottom: 18 }}>
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 16 }}><p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>Classes with active learners</p><strong style={{ fontSize: 27 }}>{classes.length}</strong></article>
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 16 }}><p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>Active teacher assignments</p><strong style={{ fontSize: 27 }}>{assignments.length}</strong></article>
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 16 }}><p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>Your assigned classes</p><strong style={{ fontSize: 27 }}>{classes.filter(c => c.assigned_to_me).length}</strong></article>
        </section>
        {canManage && <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20, marginBottom: 18 }}>
          <h2 style={{ margin: '0 0 14px', fontSize: 18 }}>Assign a class teacher</h2>
          {classes.length === 0 || teachers.length === 0 ? <p style={{ color: '#64748b' }}>Add active learners to a class and create teacher accounts before assigning class responsibility.</p> : <form onSubmit={assign} style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
            <div style={{ flex: '1 1 220px' }}><label htmlFor="class-select" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Class / form</label><select id="class-select" required value={className} onChange={e => setClassName(e.target.value)} style={{ width: '100%', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}>{classes.map(c => <option key={c.class_name} value={c.class_name}>{c.class_name} · {c.student_count} learners</option>)}</select></div>
            <div style={{ flex: '1 1 220px' }}><label htmlFor="teacher-select" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Teacher</label><select id="teacher-select" required value={teacherId} onChange={e => setTeacherId(e.target.value)} style={{ width: '100%', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}><option value="">Select teacher</option>{teachers.map(t => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
            <button disabled={saving || !teacherId} style={{ border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: '11px 16px' }}>Assign teacher</button>
          </form>}
        </section>}
        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20, marginBottom: 18 }}>
          <h2 style={{ margin: '0 0 14px', fontSize: 18 }}>Class directory</h2>
          {classes.length === 0 ? <p style={{ color: '#64748b' }}>No active class groups yet. Assign a class/form to learners in the learner directory.</p> : <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 10 }}>{classes.map(c => <article key={c.class_name} style={{ border: '1px solid #e2e8f0', borderRadius: 10, padding: 13 }}><strong>{c.class_name}</strong><p style={{ margin: '5px 0 0', color: '#64748b', fontSize: 13 }}>{c.student_count} active learners</p>{c.assigned_to_me && <p style={{ margin: '5px 0 0', color: '#067647', fontSize: 12 }}>Assigned to you</p>}</article>)}</div>}
        </section>
        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20 }}>
          <h2 style={{ margin: '0 0 14px', fontSize: 18 }}>Teacher assignments</h2>
          {assignments.length === 0 ? <p style={{ color: '#64748b' }}>No active teacher assignments yet.</p> : <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', minWidth: 560, borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead><tr>{['Class / form', 'Teacher', 'Email', ...(canManage ? [''] : [])].map((h, i) => <th key={i} style={{ padding: 10, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12 }}>{h}</th>)}</tr></thead>
            <tbody>{assignments.map(a => <tr key={a.id}><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{a.class_name}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{a.teacher_name}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{a.teacher_email}</td>{canManage && <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}><button type="button" disabled={saving} onClick={() => unassign(a.id)} style={{ border: '1px solid #fecaca', background: '#fff', color: '#b42318', borderRadius: 7, padding: '7px 9px' }}>Remove</button></td>}</tr>)}</tbody>
          </table></div>}
        </section>
      </>}
    </div>
  </main>;
}
