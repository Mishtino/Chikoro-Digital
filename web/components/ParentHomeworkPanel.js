import { useEffect, useState } from 'react';
import { api } from '../lib/api';

export default function ParentHomeworkPanel({ studentId }) {
  const [assignments, setAssignments] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    if (!studentId) { setAssignments([]); return; }
    api('/homework/parent/children/' + studentId + '/assignments')
      .then(data => { if (active) setAssignments(data.assignments || []); })
      .catch(e => { if (active) setError(e.message || 'Unable to load homework status.'); });
    return () => { active = false; };
  }, [studentId]);


  async function downloadAttachment(attachmentId) {
    try {
      const result = await api('/homework/attachments/' + attachmentId + '/download-url', { method: 'POST' });
      window.open(result.download_url, '_blank', 'noopener,noreferrer');
    } catch (e) {
      setError(e.message || 'Attachment could not be opened.');
    }
  }

  return <section style={{ marginTop: 24 }}>
    <h2>Homework and assignment status</h2>
    <p style={{ color: '#64748b' }}>Published work and submission progress for this learner.</p>
    {error && <p role="alert" style={{ color: '#b42318' }}>{error}</p>}
    {!error && !assignments.length && <p>No published homework is available for this learner right now.</p>}
    {assignments.map(item => <article key={item.id} style={{ borderTop: '1px solid #e2e8f0', padding: '14px 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <strong>{item.title}</strong>
        <span>{item.submission_status === 'not_submitted' ? 'Not submitted' : item.submission_status === 'marked' ? 'Marked' : 'Submitted'}</span>
      </div>
      <p style={{ margin: '5px 0', color: '#64748b' }}>{item.subject_name} · {item.class_name}</p>
      <p style={{ whiteSpace: 'pre-wrap' }}>{item.instructions}</p>
      <p style={{ color: '#64748b', fontSize: 13 }}>Due: {item.due_at ? new Date(item.due_at).toLocaleString() : 'No deadline set'}</p>
      {item.score !== null && item.score !== undefined && <p><strong>Score:</strong> {item.score}</p>}
      {item.feedback && <p><strong>Teacher feedback:</strong> {item.feedback}</p>}
      {!!item.attachments?.length && <div><strong>Submitted files</strong><ul>{item.attachments.map(file => <li key={file.id}><button type="button" onClick={() => downloadAttachment(file.id)} style={{ border: 0, background: 'none', color: '#2457c5', textDecoration: 'underline', cursor: 'pointer', padding: 0 }}>{file.filename}</button></li>)}</ul></div>}
    </article>)}
  </section>;
}
