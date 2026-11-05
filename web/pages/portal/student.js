import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { api, API_BASE } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function StudentHomeworkPortal() {
  const router = useRouter();
  const [assignments, setAssignments] = useState([]);
  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [uploadingId, setUploadingId] = useState('');
  const [attachmentsEnabled, setAttachmentsEnabled] = useState(false);

  async function loadAssignments() {
    const data = await api('/homework/student/assignments');
    setAssignments(data.assignments || []);
    setAttachmentsEnabled(data.attachments_enabled === true);
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
        if (active) { setAssignments(rows.assignments || []); setAttachmentsEnabled(rows.attachments_enabled === true); }
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


  async function uploadAttachment(event, item) {
    event.preventDefault();
    const form = event.currentTarget;
    const file = form.elements.namedItem('attachment')?.files?.[0];
    if (!file || !item.submission_id || uploadingId) return;
    setUploadingId(String(item.id)); setError(''); setNotice('');
    try {
      const signed = await api('/homework/student/submissions/' + item.submission_id + '/attachments/upload-url', {
        method: 'POST',
        body: JSON.stringify({ filename: file.name, content_type: file.type, size_bytes: file.size }),
      });
      const uploaded = await fetch(signed.upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': file.type, 'x-upsert': 'false' },
        body: file,
      });
      if (!uploaded.ok) throw new Error('The file could not be uploaded to secure storage.');
      await api('/homework/student/attachments/' + signed.attachment.id + '/complete', { method: 'POST' });
      await loadAssignments();
      setNotice('Your attachment was uploaded securely.');
      form.reset();
    } catch (e) {
      setError(e.message || 'The attachment could not be uploaded.');
    } finally {
      setUploadingId('');
    }
  }

  async function downloadAttachment(attachmentId) {
    const popup = window.open('about:blank', '_blank');
    if (popup) popup.opener = null;
    try {
      const result = await api('/homework/attachments/' + attachmentId + '/download-url', { method: 'POST' });
      if (popup) popup.location.href = result.download_url;
      else window.location.href = result.download_url;
    } catch (e) {
      if (popup) popup.close();
      setError(e.message || 'The attachment could not be opened.');
    }
  }


  async function downloadMyReportCard() {
    setError('');
    try {
      const { data, error: sessionError } = await getSupabaseBrowserClient().auth.getSession();
      if (sessionError || !data.session?.access_token) throw new Error('Please sign in again to download your report.');
      const response = await fetch(API_BASE + '/portal/results/pdf', {
        headers: { Authorization: 'Bearer ' + data.session.access_token },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || 'Your report card could not be downloaded.');
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'my-report-card.pdf';
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) { setError(err.message || 'Your report card could not be downloaded.'); }
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
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" onClick={downloadMyReportCard}>Download report card</button>
          <button type="button" onClick={logout}>Log out</button>
        </div>
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
          {!!item.attachments?.length && <div><strong>Your files</strong><ul>{item.attachments.map(file => <li key={file.id}><button type="button" onClick={() => downloadAttachment(file.id)} style={{ border: 0, background: 'none', color: '#2457c5', textDecoration: 'underline', cursor: 'pointer', padding: 0 }}>{file.filename}</button></li>)}</ul></div>}
          {attachmentsEnabled && <form onSubmit={event => uploadAttachment(event, item)} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 10 }}>
            <input name="attachment" type="file" required accept=".pdf,.docx,.xlsx,.pptx,.jpg,.jpeg,.png,.txt" />
            <button type="submit" disabled={uploadingId === String(item.id)}>{uploadingId === String(item.id) ? 'Uploading…' : 'Add attachment'}</button>
            <small style={{ color: '#64748b' }}>PDF, Office documents, JPG, PNG or TXT · max 10 MB each · up to 5 files</small>
          </form>}
        </div>}
      </article>)}
    </section>
  </main>;
}
