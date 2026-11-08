import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { api } from '../../lib/api';
import Brand from '../../components/Brand';
import { getSupabaseBrowserClient } from '../../lib/supabase';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export default function TimetableWorkspace() {
  const router = useRouter();
  const [profile, setProfile] = useState(null);
  const [entries, setEntries] = useState([]);
  const [terms, setTerms] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [classNames, setClassNames] = useState([]);
  const [classFilter, setClassFilter] = useState('all');
  const [dayFilter, setDayFilter] = useState('all');
  const [termFilter, setTermFilter] = useState('all');
  const [form, setForm] = useState({
    term_id: '', subject_id: '', teacher_user_id: '', class_name: '',
    day_of_week: '1', period_number: '1', start_time: '08:00', end_time: '08:40', room: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function refresh() {
    const rows = await api('/timetable/entries');
    setEntries(rows || []);
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
        const requests = [api('/fees/terms'), api('/results/subjects'), api('/timetable/entries'), api('/students')];
        if (['owner', 'headmaster'].includes(currentProfile.role)) requests.push(api('/users'));
        const results = await Promise.all(requests);
        if (!active) return;
        setProfile(currentProfile);
        setTerms(results[0] || []);
        setSubjects(results[1] || []);
        setEntries(results[2] || []);
        const forms = [...new Set((results[3] || []).filter(s => s.form).map(s => s.form))].sort();
        setClassNames(forms);
        setTeachers((results[4] || []).filter(u => u.role === 'teacher' && u.is_active));
        const currentTerm = (results[0] || []).find(t => t.is_current);
        if (currentTerm) setForm(v => ({ ...v, term_id: String(currentTerm.id) }));
        if (forms.length) setForm(v => ({ ...v, class_name: forms[0] }));
      } catch (e) { if (active) setError(e.message || 'Unable to load timetable.'); }
      finally { if (active) setLoading(false); }
    }
    load();
    return () => { active = false; };
  }, [router]);

  const canManage = ['owner', 'headmaster'].includes(profile?.role);
  const visibleEntries = useMemo(() => entries.filter(entry =>
    (classFilter === 'all' || entry.class_name === classFilter)
    && (dayFilter === 'all' || String(entry.day_of_week) === dayFilter)
    && (termFilter === 'all' || String(entry.term_id) === termFilter)
  ), [entries, classFilter, dayFilter, termFilter]);

  async function createEntry(event) {
    event.preventDefault(); setSaving(true); setError(''); setNotice('');
    try {
      await api('/timetable/entries', {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          term_id: Number(form.term_id),
          subject_id: Number(form.subject_id),
          teacher_user_id: form.teacher_user_id ? Number(form.teacher_user_id) : null,
          day_of_week: Number(form.day_of_week),
          period_number: Number(form.period_number),
          room: form.room.trim() || null,
        }),
      });
      await refresh();
      setNotice('Timetable period added.');
    } catch (e) { setError(e.message || 'Timetable period could not be added.'); }
    finally { setSaving(false); }
  }

  async function deleteEntry(id) {
    setSaving(true); setError(''); setNotice('');
    try {
      await api(`/timetable/entries/${id}`, { method: 'DELETE' });
      await refresh();
      setNotice('Timetable period removed.');
    } catch (e) { setError(e.message || 'Timetable period could not be removed.'); }
    finally { setSaving(false); }
  }

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  return <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '30px 18px', color: '#172033' }}>
    <div style={{ maxWidth: 1120, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 24 }}>
        <div><div style={{ marginBottom: 10 }}><Brand compact /></div><p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>SCHOOL WORKSPACE</p><h1 style={{ margin: '7px 0 4px' }}>Class timetable</h1><p style={{ margin: 0, color: '#64748b' }}>Manage weekly periods and avoid class, teacher and room clashes.</p></div>
        <div style={{ display: 'flex', gap: 8 }}><Link href="/school-admin" style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', textDecoration: 'none', color: '#172033', background: '#fff' }}>Dashboard</Link><button onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', background: '#fff', cursor: 'pointer' }}>Sign out</button></div>
      </header>
      {error && <p role="alert" style={{ padding: 12, background: '#fff1f0', color: '#b42318', borderRadius: 8 }}>{error}</p>}
      {notice && <p role="status" style={{ padding: 12, background: '#ecfdf3', color: '#067647', borderRadius: 8 }}>{notice}</p>}
      {loading ? <p role="status">Loading timetable…</p> : !error && <>
        {canManage && <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20, marginBottom: 18 }}>
          <h2 style={{ margin: '0 0 14px', fontSize: 18 }}>Add a timetable period</h2>
          <form onSubmit={createEntry} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(155px, 1fr))', gap: 11, alignItems: 'end' }}>
            <div><label htmlFor="tt-class" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Class / form</label><input id="tt-class" list="tt-classes" required value={form.class_name} onChange={e => setForm(v => ({ ...v, class_name: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 9, border: '1px solid #cbd5e1', borderRadius: 8 }} /><datalist id="tt-classes">{classNames.map(c => <option key={c} value={c} />)}</datalist></div>
            <div><label htmlFor="tt-term" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Term</label><select id="tt-term" required value={form.term_id} onChange={e => setForm(v => ({ ...v, term_id: e.target.value }))} style={{ width: '100%', padding: 9, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}><option value="">Select term</option>{terms.map(t => <option key={t.id} value={t.id}>{t.name} · {t.academic_year}</option>)}</select></div>
            <div><label htmlFor="tt-subject" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Subject</label><select id="tt-subject" required value={form.subject_id} onChange={e => setForm(v => ({ ...v, subject_id: e.target.value }))} style={{ width: '100%', padding: 9, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}><option value="">Select subject</option>{subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
            <div><label htmlFor="tt-teacher" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Teacher (optional)</label><select id="tt-teacher" value={form.teacher_user_id} onChange={e => setForm(v => ({ ...v, teacher_user_id: e.target.value }))} style={{ width: '100%', padding: 9, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}><option value="">Unassigned</option>{teachers.map(t => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
            <div><label htmlFor="tt-day" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Day</label><select id="tt-day" value={form.day_of_week} onChange={e => setForm(v => ({ ...v, day_of_week: e.target.value }))} style={{ width: '100%', padding: 9, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}>{DAYS.map((day, i) => <option key={day} value={i + 1}>{day}</option>)}</select></div>
            <div><label htmlFor="tt-period" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Period number</label><input id="tt-period" type="number" min="1" max="20" required value={form.period_number} onChange={e => setForm(v => ({ ...v, period_number: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 9, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <div><label htmlFor="tt-start" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Start</label><input id="tt-start" type="time" required value={form.start_time} onChange={e => setForm(v => ({ ...v, start_time: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 9, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <div><label htmlFor="tt-end" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>End</label><input id="tt-end" type="time" required value={form.end_time} onChange={e => setForm(v => ({ ...v, end_time: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 9, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <div><label htmlFor="tt-room" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Room (optional)</label><input id="tt-room" value={form.room} onChange={e => setForm(v => ({ ...v, room: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 9, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <button disabled={saving || !terms.length || !subjects.length} style={{ border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: 11 }}>Add period</button>
          </form>
        </section>}
        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>Weekly schedule</h2>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}><select aria-label="Filter timetable by term" value={termFilter} onChange={e => setTermFilter(e.target.value)} style={{ padding: 8, border: '1px solid #cbd5e1', borderRadius: 7, background: '#fff' }}><option value="all">All terms</option>{terms.map(t => <option key={t.id} value={t.id}>{t.name} · {t.academic_year}</option>)}</select><select aria-label="Filter timetable by class" value={classFilter} onChange={e => setClassFilter(e.target.value)} style={{ padding: 8, border: '1px solid #cbd5e1', borderRadius: 7, background: '#fff' }}><option value="all">All classes</option>{[...new Set(entries.map(e => e.class_name))].sort().map(c => <option key={c} value={c}>{c}</option>)}</select><select aria-label="Filter timetable by day" value={dayFilter} onChange={e => setDayFilter(e.target.value)} style={{ padding: 8, border: '1px solid #cbd5e1', borderRadius: 7, background: '#fff' }}><option value="all">All days</option>{DAYS.map((d, i) => <option key={d} value={i + 1}>{d}</option>)}</select></div>
          </div>
          {visibleEntries.length === 0 ? <p style={{ color: '#64748b' }}>No timetable periods match these filters.</p> : <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', minWidth: 760, borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead><tr>{['Day', 'Time', 'Period', 'Class', 'Subject', 'Teacher', 'Room', ...(canManage ? [''] : [])].map((h, i) => <th key={i} style={{ padding: 10, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12 }}>{h}</th>)}</tr></thead>
            <tbody>{visibleEntries.map(entry => <tr key={entry.id}>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{DAYS[entry.day_of_week - 1]}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5', whiteSpace: 'nowrap' }}>{entry.start_time}–{entry.end_time}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{entry.period_number}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{entry.class_name}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{entry.subject_name}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{entry.teacher_name || 'Unassigned'}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{entry.room || '—'}</td>
              {canManage && <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}><button type="button" disabled={saving} onClick={() => deleteEntry(entry.id)} style={{ border: '1px solid #fecaca', background: '#fff', color: '#b42318', borderRadius: 7, padding: '7px 9px' }}>Remove</button></td>}
            </tr>)}</tbody>
          </table></div>}
        </section>
      </>}
    </div>
  </main>;
}
