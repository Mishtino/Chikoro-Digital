import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';
import HomeworkTeacherPanel from '../../components/HomeworkTeacherPanel';

export default function TeacherWorkspace() {
  const router = useRouter();
  const [students, setStudents] = useState([]);
  const [terms, setTerms] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [assessments, setAssessments] = useState([]);
  const [subjectName, setSubjectName] = useState('');
  const [subjectCode, setSubjectCode] = useState('');
  const [assessment, setAssessment] = useState({ subject_id: '', term_id: '', name: '', max_score: '100', weight: '1' });
  const [selectedAssessment, setSelectedAssessment] = useState('');
  const [scores, setScores] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [conversations, setConversations] = useState([]);
  const [selectedConversationId, setSelectedConversationId] = useState('');
  const [messages, setMessages] = useState([]);
  const [messageDraft, setMessageDraft] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);

  async function refresh() {
    const [studentRows, termRows, subjectRows, assessmentRows] = await Promise.all([
      api('/students'), api('/fees/terms'), api('/results/subjects'), api('/results/assessments'),
    ]);
    setStudents(Array.isArray(studentRows) ? studentRows : []);
    setTerms(Array.isArray(termRows) ? termRows : []);
    setSubjects(Array.isArray(subjectRows) ? subjectRows : []);
    setAssessments(Array.isArray(assessmentRows) ? assessmentRows : []);
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError || !data.session?.access_token) { router.replace('/portal/login'); return; }
        const profile = await api('/auth/supabase/me');
        if (profile.role !== 'teacher' || profile.is_admin || !profile.school_id) {
          await supabase.auth.signOut();
          router.replace('/portal/login');
          return;
        }
        const [studentRows, termRows, subjectRows, assessmentRows, communicationData] = await Promise.all([
          api('/students'), api('/fees/terms'), api('/results/subjects'), api('/results/assessments'), api('/communications/conversations'),
        ]);
        if (!active) return;
        setStudents(studentRows || []);
        setTerms(termRows || []);
        setSubjects(subjectRows || []);
        setAssessments(assessmentRows || []);
        const inbox = communicationData.conversations || [];
        setConversations(inbox);
        setSelectedConversationId(inbox.length ? String(inbox[0].id) : '');
        const current = (termRows || []).find(term => term.is_current);
        if (current) setAssessment(value => ({ ...value, term_id: String(current.id) }));
      } catch (e) { if (active) setError(e.message || 'Unable to load teacher workspace.'); }
      finally { if (active) setLoading(false); }
    }
    load();
    return () => { active = false; };
  }, [router]);

  const activeStudents = useMemo(() => students.filter(student => student.status === 'active'), [students]);
  const chosenAssessment = assessments.find(item => String(item.id) === String(selectedAssessment));

  async function createSubject(event) {
    event.preventDefault(); setSaving(true); setError(''); setNotice('');
    try {
      await api('/results/subjects', { method: 'POST', body: JSON.stringify({ name: subjectName.trim(), code: subjectCode.trim() || null }) });
      setSubjectName(''); setSubjectCode('');
      await refresh();
      setNotice('Subject created.');
    } catch (e) { setError(e.message || 'Subject could not be created.'); }
    finally { setSaving(false); }
  }

  async function createAssessment(event) {
    event.preventDefault(); setSaving(true); setError(''); setNotice('');
    try {
      const result = await api('/results/assessments', {
        method: 'POST',
        body: JSON.stringify({
          subject_id: Number(assessment.subject_id),
          term_id: assessment.term_id ? Number(assessment.term_id) : null,
          name: assessment.name.trim(),
          max_score: Number(assessment.max_score),
          weight: Number(assessment.weight),
        }),
      });
      await refresh();
      setSelectedAssessment(String(result.id));
      setAssessment(current => ({ ...current, name: '' }));
      setNotice('Assessment created. You can now enter learner marks.');
    } catch (e) { setError(e.message || 'Assessment could not be created.'); }
    finally { setSaving(false); }
  }

  async function saveMarks(event) {
    event.preventDefault();
    if (!chosenAssessment) return;
    const entries = activeStudents.filter(student => scores[student.id] !== undefined && String(scores[student.id]).trim() !== '')
      .map(student => ({ student_id: student.id, assessment_id: chosenAssessment.id, score: Number(scores[student.id]) }));
    if (!entries.length) { setError('Enter at least one learner mark.'); return; }
    if (entries.some(entry => !Number.isFinite(entry.score) || entry.score < 0 || entry.score > Number(chosenAssessment.max_score))) {
      setError(`Every mark must be between 0 and ${chosenAssessment.max_score}.`); return;
    }
    setSaving(true); setError(''); setNotice('');
    try {
      const result = await api('/results/marks', { method: 'POST', body: JSON.stringify({ entries }) });
      setNotice(`${result.saved} learner mark(s) saved as drafts. A headmaster or owner must approve and publish results.`);
      setScores({});
    } catch (e) { setError(e.message || 'Marks could not be saved.'); }
    finally { setSaving(false); }
  }


  useEffect(() => {
    let active = true;
    async function loadThread() {
      if (!selectedConversationId) { setMessages([]); return; }
      try {
        const data = await api('/communications/conversations/' + selectedConversationId + '/messages');
        if (active) setMessages(data.messages || []);
      } catch (e) { if (active) setError(e.message || 'Unable to load conversation.'); }
    }
    loadThread();
    return () => { active = false; };
  }, [selectedConversationId]);

  async function sendTeacherMessage(event) {
    event.preventDefault();
    if (!selectedConversationId || !messageDraft.trim() || sendingMessage) return;
    setSendingMessage(true); setError(''); setNotice('');
    try {
      await api('/communications/conversations/' + selectedConversationId + '/messages', {
        method: 'POST', body: JSON.stringify({ body: messageDraft.trim() }),
      });
      const data = await api('/communications/conversations/' + selectedConversationId + '/messages');
      setMessages(data.messages || []);
      setMessageDraft('');
      setNotice('Reply sent to the parent.');
    } catch (e) { setError(e.message || 'Message could not be sent.'); }
    finally { setSendingMessage(false); }
  }

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  return <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '30px 18px', color: '#172033' }}>
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 24 }}>
        <div><p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>CHIKORO DIGITAL · TEACHER WORKSPACE</p><h1 style={{ margin: '7px 0 4px' }}>Academic work</h1><p style={{ margin: 0, color: '#64748b' }}>Manage subjects, assessments and draft learner marks.</p></div>
        <div style={{ display: 'flex', gap: 8 }}><a href="/school-admin/attendance" style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 13px', background: '#fff', color: '#172033', textDecoration: 'none' }}>Attendance</a><a href="/school-admin/timetable" style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 13px', background: '#fff', color: '#172033', textDecoration: 'none' }}>Timetable</a><a href="/school-admin/classes" style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 13px', background: '#fff', color: '#172033', textDecoration: 'none' }}>My classes</a><button onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 13px', background: '#fff', cursor: 'pointer' }}>Sign out</button></div>
      </header>
      {error && <p role="alert" style={{ padding: 12, borderRadius: 8, background: '#fff1f0', color: '#b42318' }}>{error}</p>}
      {notice && <p role="status" style={{ padding: 12, borderRadius: 8, background: '#ecfdf3', color: '#067647' }}>{notice}</p>}
      {loading ? <p role="status">Loading academic records…</p> : !error && <>
        <HomeworkTeacherPanel />
        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20, marginBottom: 18 }}>
          <h2 style={{ margin: '0 0 6px', fontSize: 18 }}>Parent communications</h2>
          <p style={{ color: '#64748b', fontSize: 13 }}>Only conversations for learners in your currently assigned classes appear here.</p>
          {!conversations.length ? <p>No parent messages yet.</p> : <>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: 10 }}>Conversation
              <select value={selectedConversationId} onChange={e => setSelectedConversationId(e.target.value)} style={{ display: 'block', width: '100%', maxWidth: 560, padding: 10, marginTop: 5, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}>
                {conversations.map(row => <option key={row.id} value={row.id}>{row.student_name} · {row.subject} · {row.parent_name}</option>)}
              </select>
            </label>
            <div style={{ maxHeight: 300, overflowY: 'auto', border: '1px solid #edf1f5', borderRadius: 8, padding: 10 }}>
              {messages.map(message => <div key={message.id} style={{ padding: 10, margin: '8px 0', borderRadius: 8, background: message.is_mine ? '#eff6ff' : '#f8fafc' }}>
                <strong>{message.is_mine ? 'You' : 'Parent'}</strong><p style={{ whiteSpace: 'pre-wrap', margin: '5px 0' }}>{message.body}</p><small style={{ color: '#64748b' }}>{new Date(message.created_at).toLocaleString()}</small>
              </div>)}
              {!messages.length && <p>No messages in this conversation yet.</p>}
            </div>
            <form onSubmit={sendTeacherMessage} style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
              <textarea value={messageDraft} onChange={e => setMessageDraft(e.target.value)} required maxLength={5000} rows={3} placeholder="Reply to the parent…" style={{ flex: '1 1 260px', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }} />
              <button type="submit" disabled={sendingMessage || !messageDraft.trim()} style={{ border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: '10px 14px' }}>{sendingMessage ? 'Sending…' : 'Send reply'}</button>
            </form>
          </>}
        </section>

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 18 }}>
          {[['Active learners', activeStudents.length], ['Subjects', subjects.length], ['Assessments', assessments.length], ['Academic terms', terms.length]].map(([label, value]) => <article key={label} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 17 }}><p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>{label}</p><strong style={{ fontSize: 27 }}>{value}</strong></article>)}
        </section>

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14, marginBottom: 18 }}>
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20 }}>
            <h2 style={{ margin: '0 0 14px', fontSize: 18 }}>Add subject</h2>
            <form onSubmit={createSubject}>
              <label htmlFor="subject-name" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Subject name</label>
              <input id="subject-name" required value={subjectName} onChange={e => setSubjectName(e.target.value)} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, marginBottom: 10 }} />
              <label htmlFor="subject-code" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Subject code (optional)</label>
              <input id="subject-code" value={subjectCode} onChange={e => setSubjectCode(e.target.value)} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, marginBottom: 12 }} />
              <button disabled={saving} style={{ border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: '10px 14px' }}>Add subject</button>
            </form>
          </article>
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20 }}>
            <h2 style={{ margin: '0 0 14px', fontSize: 18 }}>Create assessment</h2>
            <form onSubmit={createAssessment}>
              <label htmlFor="assessment-subject" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Subject</label>
              <select id="assessment-subject" required value={assessment.subject_id} onChange={e => setAssessment(v => ({ ...v, subject_id: e.target.value }))} style={{ width: '100%', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, marginBottom: 10, background: '#fff' }}><option value="">Select subject</option>{subjects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
              <label htmlFor="assessment-term" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Term</label>
              <select id="assessment-term" value={assessment.term_id} onChange={e => setAssessment(v => ({ ...v, term_id: e.target.value }))} style={{ width: '100%', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, marginBottom: 10, background: '#fff' }}><option value="">No term selected</option>{terms.map(item => <option key={item.id} value={item.id}>{item.name} · {item.academic_year}</option>)}</select>
              <label htmlFor="assessment-name" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Assessment name</label>
              <input id="assessment-name" required value={assessment.name} onChange={e => setAssessment(v => ({ ...v, name: e.target.value }))} style={{ width: '100%', padding: 10, boxSizing: 'border-box', border: '1px solid #cbd5e1', borderRadius: 8, marginBottom: 10 }} />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div><label htmlFor="max-score" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Maximum score</label><input id="max-score" type="number" min="0.01" step="0.01" required value={assessment.max_score} onChange={e => setAssessment(v => ({ ...v, max_score: e.target.value }))} style={{ width: '100%', padding: 10, boxSizing: 'border-box', border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
                <div><label htmlFor="weight" style={{ display: 'block', fontWeight: 600, marginBottom: 5 }}>Weight</label><input id="weight" type="number" min="0.01" step="0.01" required value={assessment.weight} onChange={e => setAssessment(v => ({ ...v, weight: e.target.value }))} style={{ width: '100%', padding: 10, boxSizing: 'border-box', border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
              </div>
              <button disabled={saving || !subjects.length} style={{ marginTop: 12, border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: '10px 14px' }}>Create assessment</button>
            </form>
          </article>
        </section>

        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20 }}>
          <h2 style={{ margin: '0 0 6px', fontSize: 18 }}>Enter learner marks</h2>
          <p style={{ color: '#64748b', fontSize: 13, margin: '0 0 14px' }}>Marks are saved as drafts. Only a school owner or headmaster can approve and publish them.</p>
          <label htmlFor="mark-assessment" style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Assessment</label>
          <select id="mark-assessment" value={selectedAssessment} onChange={e => { setSelectedAssessment(e.target.value); setScores({}); }} style={{ width: '100%', maxWidth: 500, padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff', marginBottom: 14 }}><option value="">Select assessment</option>{assessments.map(item => <option key={item.id} value={item.id}>{item.name} · {subjects.find(subject => subject.id === item.subject_id)?.name || 'Subject'} · max {item.max_score}</option>)}</select>
          {!chosenAssessment ? <p style={{ color: '#64748b' }}>Choose an assessment to enter marks.</p> : activeStudents.length === 0 ? <p style={{ color: '#64748b' }}>No active learners are registered.</p> : <form onSubmit={saveMarks}>
            <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: 550 }}>
              <thead><tr>{['Student number', 'Learner', `Score / ${chosenAssessment.max_score}`].map(label => <th key={label} style={{ padding: 10, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12 }}>{label}</th>)}</tr></thead>
              <tbody>{activeStudents.map(student => <tr key={student.id}><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{student.student_number}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{student.first_name} {student.last_name}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}><input aria-label={`Score for ${student.first_name} ${student.last_name}`} type="number" min="0" max={chosenAssessment.max_score} step="0.01" value={scores[student.id] ?? ''} onChange={e => setScores(v => ({ ...v, [student.id]: e.target.value }))} style={{ width: 130, padding: 8, border: '1px solid #cbd5e1', borderRadius: 7 }} /></td></tr>)}</tbody>
            </table></div>
            <button disabled={saving} type="submit" style={{ marginTop: 14, border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: '11px 15px', fontWeight: 600 }}>{saving ? 'Saving marks…' : 'Save draft marks'}</button>
          </form>}
        </section>
      </>}
    </div>
  </main>;
}
