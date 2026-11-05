import { useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api';

export default function HomeworkTeacherPanel() {
  const [students, setStudents] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [submissions, setSubmissions] = useState([]);
  const [form, setForm] = useState({ class_name: '', subject_id: '', title: '', instructions: '', due_at: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const classes = useMemo(() => [...new Set(students.map(s => s.form).filter(Boolean))].sort(), [students]);

  async function loadAssignments() {
    const data = await api('/homework/assignments');
    const rows = data.assignments || [];
    setAssignments(rows);
    return rows;
  }

  async function loadSubmissions(id) {
    if (!id) { setSubmissions([]); return; }
    const data = await api('/homework/assignments/' + id + '/submissions');
    setSubmissions(data.submissions || []);
  }

  useEffect(() => {
    let active = true;
    Promise.all([api('/students'), api('/results/subjects'), api('/homework/assignments')])
      .then(([studentRows, subjectRows, homeworkRows]) => {
        if (!active) return;
        setStudents(studentRows || []);
        setSubjects(subjectRows || []);
        const rows = homeworkRows.assignments || [];
        setAssignments(rows);
        setSelectedId(rows.length ? String(rows[0].id) : '');
        setForm(value => ({
          ...value,
          class_name: (studentRows || []).find(s => s.form)?.form || '',
          subject_id: subjectRows?.length ? String(subjectRows[0].id) : '',
        }));
      })
      .catch(e => { if (active) setError(e.message || 'Unable to load homework workspace.'); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    if (selectedId) {
      loadSubmissions(selectedId).catch(e => { if (active) setError(e.message || 'Unable to load submissions.'); });
    } else setSubmissions([]);
    return () => { active = false; };
  }, [selectedId]);

  async function create(event) {
    event.preventDefault();
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await api('/homework/assignments', {
        method: 'POST',
        body: JSON.stringify({
          class_name: form.class_name, subject_id: Number(form.subject_id),
          title: form.title.trim(), instructions: form.instructions.trim(),
          due_at: form.due_at || null, publish: true,
        }),
      });
      const rows = await loadAssignments();
      setSelectedId(String(result.id));
      setForm(value => ({ ...value, title: '', instructions: '', due_at: '' }));
      setNotice('Homework published to ' + form.class_name + '.');
    } catch (e) { setError(e.message || 'Homework could not be published.'); }
    finally { setBusy(false); }
  }

  async function mark(event, submission) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true); setError(''); setNotice('');
    try {
      await api('/homework/submissions/' + submission.id + '/mark', {
        method: 'POST',
        body: JSON.stringify({
          score: data.get('score') === '' ? null : Number(data.get('score')),
          feedback: data.get('feedback') || null,
        }),
      });
      await loadSubmissions(selectedId);
      setNotice('Feedback saved for ' + submission.student_name + '.');
    } catch (e) { setError(e.message || 'Feedback could not be saved.'); }
    finally { setBusy(false); }
  }

  return <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20, marginBottom: 18 }}>
    <h2 style={{ margin: '0 0 6px', fontSize: 18 }}>Homework and assignments</h2>
    <p style={{ color: '#64748b', fontSize: 13 }}>Publish work to your assigned classes, then review and mark learner submissions. Text answers are supported in this release.</p>
    {error && <p role="alert" style={{ color: '#b42318' }}>{error}</p>}
    {notice && <p role="status" style={{ color: '#067647' }}>{notice}</p>}
    <form onSubmit={create} style={{ display: 'grid', gap: 10, maxWidth: 720 }}>
      <label>Class<select required value={form.class_name} onChange={e => setForm(v => ({ ...v, class_name: e.target.value }))} style={{ display: 'block', width: '100%', padding: 10 }}>
        <option value="">Select class</option>{classes.map(name => <option key={name} value={name}>{name}</option>)}
      </select></label>
      <label>Subject<select required value={form.subject_id} onChange={e => setForm(v => ({ ...v, subject_id: e.target.value }))} style={{ display: 'block', width: '100%', padding: 10 }}>
        <option value="">Select subject</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
      </select></label>
      <label>Title<input required maxLength={160} value={form.title} onChange={e => setForm(v => ({ ...v, title: e.target.value }))} style={{ display: 'block', width: '100%', padding: 10 }} /></label>
      <label>Instructions<textarea required maxLength={10000} rows={4} value={form.instructions} onChange={e => setForm(v => ({ ...v, instructions: e.target.value }))} style={{ display: 'block', width: '100%', padding: 10 }} /></label>
      <label>Due date and time<input type="datetime-local" value={form.due_at} onChange={e => setForm(v => ({ ...v, due_at: e.target.value }))} style={{ display: 'block', padding: 10 }} /></label>
      <button type="submit" disabled={busy || !classes.length || !subjects.length} style={{ justifySelf: 'start', padding: '10px 16px' }}>{busy ? 'Saving…' : 'Publish homework'}</button>
    </form>
    <div style={{ marginTop: 22 }}>
      <label style={{ display: 'block', fontWeight: 600, marginBottom: 8 }}>Review submissions<select value={selectedId} onChange={e => setSelectedId(e.target.value)} style={{ display: 'block', width: '100%', maxWidth: 600, padding: 10, marginTop: 4 }}>
        <option value="">Select assignment</option>{assignments.map(item => <option key={item.id} value={item.id}>{item.class_name} · {item.title}</option>)}
      </select></label>
      {!selectedId ? <p>No assignments available yet.</p> : !submissions.length ? <p>No learner submissions yet.</p> : submissions.map(sub => <div key={sub.id} style={{ borderTop: '1px solid #e2e8f0', padding: '14px 0' }}>
        <strong>{sub.student_name} · {sub.student_number}</strong>
        <p style={{ whiteSpace: 'pre-wrap' }}>{sub.answer_text}</p>
        <p style={{ color: '#64748b', fontSize: 12 }}>Status: {sub.status} · Submitted: {new Date(sub.submitted_at).toLocaleString()}</p>
        <form onSubmit={event => mark(event, sub)} style={{ display: 'grid', gap: 8, maxWidth: 600 }}>
          <label>Score<input name="score" type="number" min="0" step="0.01" defaultValue={sub.score ?? ''} style={{ display: 'block', padding: 8 }} /></label>
          <label>Feedback<textarea name="feedback" rows={2} defaultValue={sub.feedback || ''} style={{ display: 'block', width: '100%', padding: 8 }} /></label>
          <button type="submit" disabled={busy} style={{ justifySelf: 'start', padding: '8px 12px' }}>Save feedback</button>
        </form>
      </div>)}
    </div>
  </section>;
}
