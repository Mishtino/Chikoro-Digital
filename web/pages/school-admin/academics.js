import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function SchoolAcademics() {
  const router = useRouter();
  const [terms, setTerms] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [assessments, setAssessments] = useState([]);
  const [marks, setMarks] = useState([]);
  const [termForm, setTermForm] = useState({ name: '', academic_year: '', start_date: '', end_date: '', is_current: false });
  const [termFilter, setTermFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyAssessment, setBusyAssessment] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function refresh() {
    const [termRows, subjectRows, assessmentRows, markRows] = await Promise.all([
      api('/fees/terms'), api('/results/subjects'), api('/results/assessments'), api('/results/marks'),
    ]);
    setTerms(termRows || []);
    setSubjects(subjectRows || []);
    setAssessments(assessmentRows || []);
    setMarks(markRows || []);
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
        const [termRows, subjectRows, assessmentRows, markRows] = await Promise.all([
          api('/fees/terms'), api('/results/subjects'), api('/results/assessments'), api('/results/marks'),
        ]);
        if (!active) return;
        setTerms(termRows || []);
        setSubjects(subjectRows || []);
        setAssessments(assessmentRows || []);
        setMarks(markRows || []);
      } catch (e) { if (active) setError(e.message || 'Unable to load academic records.'); }
      finally { if (active) setLoading(false); }
    }
    load();
    return () => { active = false; };
  }, [router]);

  const subjectById = useMemo(() => new Map(subjects.map(item => [item.id, item.name])), [subjects]);
  const visibleMarks = marks.filter(mark =>
    (termFilter === 'all' || String(mark.term_id) === termFilter)
    && (statusFilter === 'all' || mark.status === statusFilter)
  );
  const assessmentSummary = assessments.map(item => {
    const related = marks.filter(mark => mark.assessment_id === item.id);
    return {
      ...item,
      subject_name: subjectById.get(item.subject_id) || 'Subject',
      draft: related.filter(mark => mark.status === 'draft').length,
      approved: related.filter(mark => mark.status === 'approved').length,
      published: related.filter(mark => mark.status === 'published').length,
    };
  });

  async function createTerm(event) {
    event.preventDefault(); setSaving(true); setError(''); setNotice('');
    try {
      await api('/fees/terms', {
        method: 'POST',
        body: JSON.stringify({
          name: termForm.name.trim(),
          academic_year: termForm.academic_year.trim(),
          start_date: termForm.start_date || null,
          end_date: termForm.end_date || null,
          is_current: termForm.is_current,
        }),
      });
      setTermForm({ name: '', academic_year: '', start_date: '', end_date: '', is_current: false });
      await refresh();
      setNotice('Academic term created.');
    } catch (e) { setError(e.message || 'Term could not be created.'); }
    finally { setSaving(false); }
  }

  async function reviewAssessment(assessmentId, action) {
    setBusyAssessment(assessmentId); setError(''); setNotice('');
    try {
      const result = await api(`/results/marks/${action}?assessment_id=${assessmentId}`, { method: 'POST' });
      await refresh();
      setNotice(action === 'approve' ? `${result.approved} mark(s) approved.` : `${result.published} mark(s) published.`);
    } catch (e) { setError(e.message || 'The mark review action could not be completed.'); }
    finally { setBusyAssessment(null); }
  }

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  return <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '30px 18px', color: '#172033' }}>
    <div style={{ maxWidth: 1120, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 24 }}>
        <div><p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>CHIKORO DIGITAL · ACADEMIC MANAGEMENT</p><h1 style={{ margin: '7px 0 4px' }}>Terms & results</h1><p style={{ margin: 0, color: '#64748b' }}>Configure terms and review teacher-submitted marks.</p></div>
        <div style={{ display: 'flex', gap: 9 }}><Link href="/school-admin" style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', textDecoration: 'none', color: '#172033', background: '#fff' }}>Dashboard</Link><button onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', background: '#fff', cursor: 'pointer' }}>Sign out</button></div>
      </header>
      {error && <p role="alert" style={{ padding: 12, background: '#fff1f0', color: '#b42318', borderRadius: 8 }}>{error}</p>}
      {notice && <p role="status" style={{ padding: 12, background: '#ecfdf3', color: '#067647', borderRadius: 8 }}>{notice}</p>}
      {loading ? <p role="status">Loading academic management…</p> : !error && <>
        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22, marginBottom: 18 }}>
          <h2 style={{ margin: '0 0 14px', fontSize: 19 }}>Create academic term</h2>
          <form onSubmit={createTerm} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, alignItems: 'end' }}>
            <div><label htmlFor="term-name" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Term name</label><input id="term-name" required value={termForm.name} onChange={e => setTermForm(v => ({ ...v, name: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <div><label htmlFor="term-year" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Academic year</label><input id="term-year" required value={termForm.academic_year} onChange={e => setTermForm(v => ({ ...v, academic_year: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <div><label htmlFor="term-start" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Start date</label><input id="term-start" type="date" value={termForm.start_date} onChange={e => setTermForm(v => ({ ...v, start_date: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <div><label htmlFor="term-end" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>End date</label><input id="term-end" type="date" value={termForm.end_date} onChange={e => setTermForm(v => ({ ...v, end_date: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 10 }}><input type="checkbox" checked={termForm.is_current} onChange={e => setTermForm(v => ({ ...v, is_current: e.target.checked }))} /> Set as current term</label>
            <button disabled={saving} style={{ border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: 11 }}>Create term</button>
          </form>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 16 }}>{terms.map(term => <span key={term.id} style={{ background: term.is_current ? '#ecfdf3' : '#f1f5f9', color: term.is_current ? '#067647' : '#475569', borderRadius: 7, padding: '7px 10px', fontSize: 13 }}>{term.name} · {term.academic_year}{term.is_current ? ' · Current' : ''}</span>)}</div>
        </section>

        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22, marginBottom: 18 }}>
          <h2 style={{ margin: '0 0 14px', fontSize: 19 }}>Assessment review</h2>
          {assessmentSummary.length === 0 ? <p style={{ color: '#64748b' }}>No assessments have been created yet. Teachers can create subjects and assessments in their academic workspace.</p> : <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: 750 }}>
            <thead><tr>{['Assessment', 'Subject', 'Draft', 'Approved', 'Published', 'Actions'].map(label => <th key={label} style={{ padding: 10, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12 }}>{label}</th>)}</tr></thead>
            <tbody>{assessmentSummary.map(item => <tr key={item.id}>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5', fontWeight: 600 }}>{item.name}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{item.subject_name}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{item.draft}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{item.approved}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{item.published}</td>
              <td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}><div style={{ display: 'flex', gap: 7 }}><button type="button" disabled={!item.draft || busyAssessment === item.id} onClick={() => reviewAssessment(item.id, 'approve')} style={{ border: '1px solid #cbd5e1', background: '#fff', borderRadius: 7, padding: '7px 9px' }}>Approve</button><button type="button" disabled={!item.approved || busyAssessment === item.id} onClick={() => reviewAssessment(item.id, 'publish')} style={{ border: 0, background: '#2457c5', color: '#fff', borderRadius: 7, padding: '7px 9px' }}>Publish</button></div></td>
            </tr>)}</tbody>
          </table></div>}
        </section>

        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
            <h2 style={{ margin: 0, fontSize: 19 }}>Learner marks</h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <select aria-label="Filter marks by term" value={termFilter} onChange={e => setTermFilter(e.target.value)} style={{ padding: 8, border: '1px solid #cbd5e1', borderRadius: 7, background: '#fff' }}><option value="all">All terms</option>{terms.map(term => <option key={term.id} value={term.id}>{term.name} · {term.academic_year}</option>)}</select>
              <select aria-label="Filter marks by status" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ padding: 8, border: '1px solid #cbd5e1', borderRadius: 7, background: '#fff' }}><option value="all">All statuses</option><option value="draft">Draft</option><option value="approved">Approved</option><option value="published">Published</option></select>
            </div>
          </div>
          {visibleMarks.length === 0 ? <p style={{ color: '#64748b' }}>No marks match these filters.</p> : <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: 700 }}>
            <thead><tr>{['Learner', 'Assessment', 'Subject', 'Score', 'Status'].map(label => <th key={label} style={{ padding: 10, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12 }}>{label}</th>)}</tr></thead>
            <tbody>{visibleMarks.map(mark => <tr key={mark.id}><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{mark.student_name} · {mark.student_number}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{mark.assessment_name}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{mark.subject_name}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{mark.score} / {mark.max_score}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5', textTransform: 'capitalize' }}>{mark.status}</td></tr>)}</tbody>
          </table></div>}
        </section>
      </>}
    </div>
  </main>;
}
