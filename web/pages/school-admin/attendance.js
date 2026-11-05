import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

const todayHarare = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Africa/Harare', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());

export default function AttendanceWorkspace() {
  const router = useRouter();
  const [students, setStudents] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [roster, setRoster] = useState([]);
  const [className, setClassName] = useState('');
  const [attendanceDate, setAttendanceDate] = useState(todayHarare());
  const [termId, setTermId] = useState('');
  const [terms, setTerms] = useState([]);
  const [statuses, setStatuses] = useState({});
  const [notes, setNotes] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function refreshSessions() {
    const rows = await api('/attendance/sessions');
    setSessions(rows || []);
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError || !data.session?.access_token) { router.replace('/portal/login'); return; }
        const profile = await api('/auth/supabase/me');
        if (!['owner', 'headmaster', 'teacher'].includes(profile.role) || profile.is_admin || !profile.school_id) {
          await supabase.auth.signOut();
          router.replace('/portal/login');
          return;
        }
        const [studentRows, termRows, sessionRows] = await Promise.all([
          api('/students'), api('/fees/terms'), api('/attendance/sessions'),
        ]);
        if (!active) return;
        setStudents(studentRows || []);
        setTerms(termRows || []);
        setSessions(sessionRows || []);
        const forms = [...new Set((studentRows || []).filter(s => s.status === 'active' && s.form).map(s => s.form))].sort();
        if (forms.length) setClassName(forms[0]);
        const current = (termRows || []).find(t => t.is_current);
        if (current) setTermId(String(current.id));
      } catch (e) { if (active) setError(e.message || 'Unable to load attendance workspace.'); }
      finally { if (active) setLoading(false); }
    }
    load();
    return () => { active = false; };
  }, [router]);

  const forms = useMemo(() => [...new Set(students.filter(s => s.status === 'active' && s.form).map(s => s.form))].sort(), [students]);
  const activeSession = sessions.find(s => String(s.id) === selectedId);
  const rosterCount = roster.length;
  const markedCount = roster.filter(s => statuses[s.student_id]).length;

  async function createRegister(event) {
    event.preventDefault(); setSaving(true); setError(''); setNotice('');
    try {
      const created = await api('/attendance/sessions', {
        method: 'POST',
        body: JSON.stringify({ class_name: className, attendance_date: attendanceDate, term_id: termId ? Number(termId) : null }),
      });
      await refreshSessions();
      setSelectedId(String(created.id));
      await openRegister(String(created.id));
      setNotice('Attendance register created.');
    } catch (e) { setError(e.message || 'Register could not be created.'); }
    finally { setSaving(false); }
  }

  async function openRegister(id) {
    setError(''); setNotice('');
    try {
      const result = await api(`/attendance/sessions/${id}/records`);
      setSelectedId(String(id));
      setRoster(result.students || []);
      const nextStatuses = {}, nextNotes = {};
      (result.students || []).forEach(student => {
        if (student.status) nextStatuses[student.student_id] = student.status;
        if (student.note) nextNotes[student.student_id] = student.note;
      });
      setStatuses(nextStatuses);
      setNotes(nextNotes);
    } catch (e) { setError(e.message || 'Register could not be opened.'); }
  }

  async function saveRegister() {
    if (!activeSession || activeSession.status !== 'draft') return;
    const entries = roster.filter(s => statuses[s.student_id]).map(s => ({
      student_id: s.student_id, status: statuses[s.student_id], note: notes[s.student_id] || null,
    }));
    if (entries.length !== roster.length) { setError('Select an attendance status for every active learner before saving.'); return; }
    setSaving(true); setError(''); setNotice('');
    try {
      await api(`/attendance/sessions/${selectedId}/records`, { method: 'PUT', body: JSON.stringify({ entries }) });
      await refreshSessions();
      setNotice(`Saved attendance for ${entries.length} learners.`);
    } catch (e) { setError(e.message || 'Attendance could not be saved.'); }
    finally { setSaving(false); }
  }

  async function submitRegister() {
    if (!activeSession || activeSession.status !== 'draft') return;
    setSaving(true); setError(''); setNotice('');
    try {
      const result = await api(`/attendance/sessions/${selectedId}/submit`, { method: 'POST' });
      await refreshSessions();
      await openRegister(selectedId);
      setNotice(`Register submitted for ${result.learner_count} learners. It is now read-only.`);
    } catch (e) { setError(e.message || 'Register could not be submitted.'); }
    finally { setSaving(false); }
  }

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  return <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '30px 18px', color: '#172033' }}>
    <div style={{ maxWidth: 1120, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 24 }}>
        <div><p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>CHIKORO DIGITAL · SCHOOL OPERATIONS</p><h1 style={{ margin: '7px 0 4px' }}>Attendance register</h1><p style={{ margin: 0, color: '#64748b' }}>Record daily class attendance and submit a complete register.</p></div>
        <div style={{ display: 'flex', gap: 9 }}><Link href="/school-admin" style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', textDecoration: 'none', color: '#172033', background: '#fff' }}>Dashboard</Link><button onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', background: '#fff', cursor: 'pointer' }}>Sign out</button></div>
      </header>
      {error && <p role="alert" style={{ padding: 12, background: '#fff1f0', color: '#b42318', borderRadius: 8 }}>{error}</p>}
      {notice && <p role="status" style={{ padding: 12, background: '#ecfdf3', color: '#067647', borderRadius: 8 }}>{notice}</p>}
      {loading ? <p role="status">Loading attendance records…</p> : !error && <>
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 18 }}>
          {[['Registers', sessions.length], ['Active classes', forms.length], ['Learners in selected register', rosterCount], ['Marked', markedCount]].map(([label, value]) => <article key={label} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 16 }}><p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>{label}</p><strong style={{ fontSize: 26 }}>{value}</strong></article>)}
        </section>
        <section style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, .8fr) minmax(0, 1.5fr)', gap: 16, alignItems: 'start' }}>
          <div style={{ display: 'grid', gap: 14 }}>
            <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 18 }}>
              <h2 style={{ margin: '0 0 14px', fontSize: 18 }}>Create register</h2>
              {forms.length === 0 ? <p style={{ color: '#64748b' }}>Add active learners and assign them to a class/form before creating a register.</p> : <form onSubmit={createRegister}>
                <label htmlFor="attendance-class" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Class / form</label>
                <select id="attendance-class" required value={className} onChange={e => setClassName(e.target.value)} style={{ width: '100%', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff', marginBottom: 10 }}>{forms.map(form => <option key={form} value={form}>{form}</option>)}</select>
                <label htmlFor="attendance-date" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Date</label>
                <input id="attendance-date" type="date" required value={attendanceDate} onChange={e => setAttendanceDate(e.target.value)} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, marginBottom: 10 }} />
                <label htmlFor="attendance-term" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Academic term (optional)</label>
                <select id="attendance-term" value={termId} onChange={e => setTermId(e.target.value)} style={{ width: '100%', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff', marginBottom: 12 }}><option value="">No term</option>{terms.map(t => <option key={t.id} value={t.id}>{t.name} · {t.academic_year}</option>)}</select>
                <button disabled={saving} style={{ width: '100%', border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: 11 }}>Create register</button>
              </form>}
            </article>
            <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 18 }}>
              <h2 style={{ margin: '0 0 12px', fontSize: 18 }}>Recent registers</h2>
              {sessions.length === 0 ? <p style={{ color: '#64748b' }}>No registers have been created yet.</p> : <div style={{ display: 'grid', gap: 8 }}>{sessions.map(session => <button key={session.id} type="button" onClick={() => openRegister(String(session.id))} style={{ textAlign: 'left', border: selectedId === String(session.id) ? '2px solid #2457c5' : '1px solid #e2e8f0', borderRadius: 9, padding: 11, background: '#fff', cursor: 'pointer' }}><strong>{session.class_name}</strong><span style={{ display: 'block', color: '#64748b', fontSize: 13 }}>{session.attendance_date} · {session.record_count} marked · {session.status}</span></button>)}</div>}
            </article>
          </div>
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 18, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
              <div><h2 style={{ margin: 0, fontSize: 18 }}>{activeSession ? `${activeSession.class_name} · ${activeSession.attendance_date}` : 'Learner attendance'}</h2><p style={{ margin: '5px 0 0', color: '#64748b', fontSize: 13 }}>{activeSession ? `${activeSession.status === 'draft' ? 'Draft register' : 'Submitted · read-only'}` : 'Select or create a register to begin.'}</p></div>
              {activeSession && <span style={{ borderRadius: 7, background: activeSession.status === 'submitted' ? '#ecfdf3' : '#fff7ed', color: activeSession.status === 'submitted' ? '#067647' : '#9a3412', padding: '7px 9px', fontSize: 12 }}>{activeSession.status}</span>}
            </div>
            {!selectedId ? <p style={{ color: '#64748b' }}>Choose a register from the left to see its learner list.</p> : roster.length === 0 ? <p style={{ color: '#64748b' }}>No active learners are assigned to this class/form.</p> : <>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, fontSize: 12, color: '#64748b' }}><span>Present: {Object.values(statuses).filter(s => s === 'present').length}</span><span>Absent: {Object.values(statuses).filter(s => s === 'absent').length}</span><span>Late: {Object.values(statuses).filter(s => s === 'late').length}</span><span>Excused: {Object.values(statuses).filter(s => s === 'excused').length}</span></div>
              <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', minWidth: 650, borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead><tr>{['Learner', 'Student number', 'Status', 'Note'].map(label => <th key={label} style={{ padding: 9, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12 }}>{label}</th>)}</tr></thead>
                <tbody>{roster.map(student => <tr key={student.student_id}>
                  <td style={{ padding: 9, borderBottom: '1px solid #edf1f5' }}>{student.first_name} {student.last_name}</td>
                  <td style={{ padding: 9, borderBottom: '1px solid #edf1f5' }}>{student.student_number}</td>
                  <td style={{ padding: 9, borderBottom: '1px solid #edf1f5' }}><select aria-label={`Attendance status for ${student.first_name} ${student.last_name}`} disabled={activeSession?.status !== 'draft'} value={statuses[student.student_id] || ''} onChange={e => setStatuses(v => ({ ...v, [student.student_id]: e.target.value }))} style={{ padding: 8, border: '1px solid #cbd5e1', borderRadius: 7, background: '#fff' }}><option value="">Select</option><option value="present">Present</option><option value="absent">Absent</option><option value="late">Late</option><option value="excused">Excused</option></select></td>
                  <td style={{ padding: 9, borderBottom: '1px solid #edf1f5' }}><input aria-label={`Note for ${student.first_name} ${student.last_name}`} disabled={activeSession?.status !== 'draft'} value={notes[student.student_id] || ''} onChange={e => setNotes(v => ({ ...v, [student.student_id]: e.target.value }))} placeholder="Optional" style={{ width: '100%', minWidth: 110, boxSizing: 'border-box', padding: 8, border: '1px solid #cbd5e1', borderRadius: 7 }} /></td>
                </tr>)}</tbody>
              </table></div>
              {activeSession?.status === 'draft' && <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 9, flexWrap: 'wrap', marginTop: 14 }}><button type="button" disabled={saving} onClick={saveRegister} style={{ border: '1px solid #cbd5e1', background: '#fff', borderRadius: 8, padding: '10px 13px' }}>{saving ? 'Saving…' : 'Save attendance'}</button><button type="button" disabled={saving || markedCount !== rosterCount || rosterCount === 0} onClick={submitRegister} style={{ border: 0, background: '#2457c5', color: '#fff', borderRadius: 8, padding: '10px 13px' }}>Submit register</button></div>}
            </>}
          </article>
        </section>
      </>}
    </div>
  </main>;
}
