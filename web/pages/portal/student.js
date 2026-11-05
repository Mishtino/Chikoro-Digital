import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function StudentHomeworkPortal() {
  const router = useRouter();
  const [assignments, setAssignments] = useState([]);
  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function loadAssignments() {
    const data = await api('/homework/student/assignments');
    setAssignments(data.assignments || []);
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const { data, error: sessionError } = await getSupabaseBrowserClient().auth.getSession();
        if (sessionError || !data.session?.access_token) {
          router.replace('/portal/login');
          return;
        }
        const profile = await api('/auth/supabase/me');
        if (profile.role !== 'student' || profile.is_admin || !profile.school_id) {
          router.replace('/portal/login');
          return;
        }
        const rows = await api('/homework/student/assignments');
        if (active) setAssignments(rows.assignments || []);
      } catch (e) {
        if (active) setError(e.message || 'Unable to load your homework.');
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, [router]);

  async function submit(event, assignmentId) {
    event.preventDefault();
    const answer = (answers[assignmentId] || '').trim();
    if (!answer || savingId) return;
    setSavingId(String(assignmentId));
    setError('');
    setNotice('');
    try {
      await api('/homework/student/assignments/' + assignmentId + '/submit', {
        method: 'POST',
        body: JSON.stringify({ answer_text: answer }),
      });
      await loadAssignments();
      setAnswers(value => ({ ...value, [assignmentId]: '' }));
      setNotice('Your homework was submitted successfully.');
    } catch (e) {
      setError(e.message || 'Your homework could not be submitted.');
    } finally {
      setSavingId('');
    }
  }

  async function logout() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  if (loading) return <main className="container"><section className="card" role="status">Loading your homework…</section></main>;

  return <main className="container" style={{ maxWidth: 900, margin: '2rem auto', padding: '0 1rem' }}>
    <section className="card">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div><p style={{ margin: 0, opacity: .7 }}>CHIKORO DIGITAL · STUDENT PORTAL</p><h1 style={{ margin: '8px 0' }}>My homework</h1><p style={{ margin: 0 }}>View class assignments, submit your work and read teacher feedback.</p></div>
        <button type="button" onClick={logout}>Log out</button>
      </header>
      {error && <p role="alert" style={{ color: '#b42318', marginTop: 18 }}>{error}</p>}
      {notice && <p role="status" style={{ color: '#067647', marginTop: 18 }}>{notice}</p>}
      {!assignments.length ? <p style={{ marginTop: 24 }}>There are no published assignments for your class right now.</p> : assignments.map(item => <article key={item.id} style={{ borderTop: '1px solid #e2e8f0', marginTop: 20, paddingTop: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div><h2 style={{ margin: '0 0 5px', fontSize: 20 }}>{item.title}</h2><p style={{ margin: 0, color: '#64748b' }}>{item.subject_name} · {item.class_name}</p></div>
          <strong>{item.submission_status === 'not_submitted' ? 'Not submitted' : item.submission_status === 'marked' ? 'Marked' : 'Submitted'}</strong>
        </div>
        <p style={{ whiteSpace: 'pre-wrap' }}>{item.instructions}</p>
        <p style={{ color: '#64748b', fontSize: 13 }}>Due: {item.due_at ? new Date(item.due_at).toLocaleString() : 'No deadline set'}</p>
        {item.submission_status === 'not_submitted' ? <form onSubmit={event => submit(event, item.id)} style={{ display: 'grid', gap: 10 }}>
          <label>Your answer<textarea required maxLength={20000} rows={5} value={answers[item.id] || ''} onChange={event => setAnswers(value => ({ ...value, [item.id]: event.target.value }))} style={{ display: 'block', width: '100%', padding: 12, marginTop: 6 }} /></label>
          <button type="submit" disabled={savingId === String(item.id) || !(answers[item.id] || '').trim()} style={{ justifySelf: 'start', padding: '10px 16px' }}>{savingId === String(item.id) ? 'Submitting…' : 'Submit homework'}</button>
        </form> : <div style={{ background: '#f8fafc', borderRadius: 8, padding: 12 }}>
          <p style={{ margin: 0 }}>Submission received{item.submitted_at ? ' · ' + new Date(item.submitted_at).toLocaleString() : ''}.</p>
          {item.score !== null && item.score !== undefined && <p><strong>Score:</strong> {item.score}</p>}
          {item.feedback && <p><strong>Teacher feedback:</strong> {item.feedback}</p>}
        </div>}
      </article>)}
    </section>
  </main>;
}
