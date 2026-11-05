import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function ParentPortal() {
  const router = useRouter();
  const [children, setChildren] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [fees, setFees] = useState(null);
  const [results, setResults] = useState(null);
  const [attendance, setAttendance] = useState(null);
  const [teachers, setTeachers] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [selectedConversationId, setSelectedConversationId] = useState('');
  const [messages, setMessages] = useState([]);
  const [messageDraft, setMessageDraft] = useState('');
  const [messageSubject, setMessageSubject] = useState('');
  const [selectedTeacherId, setSelectedTeacherId] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [terms, setTerms] = useState([]);
  const [selectedTermId, setSelectedTermId] = useState('');
  const [termsLoaded, setTermsLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [paymentError, setPaymentError] = useState('');
  const [paying, setPaying] = useState(false);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const { data, error: sessionError } = await getSupabaseBrowserClient().auth.getSession();
        if (sessionError || !data.session) {
          router.replace('/portal/login');
          return;
        }
        const response = await api('/portal/parent/children');
        if (!active) return;
        setChildren(response.children || []);
        if (response.children && response.children.length) {
          setSelectedId(String(response.children[0].id));
        }
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, [router]);

  useEffect(() => {
    let active = true;
    async function loadChild() {
      if (!selectedId) {
        setFees(null);
        setResults(null);
        setAttendance(null);
        setTerms([]);
        setSelectedTermId('');
        setTermsLoaded(false);
        setPaymentError('');
        return;
      }
      setError('');
      setFees(null);
      setResults(null);
      setAttendance(null);
      setTerms([]);
      setSelectedTermId('');
      setTermsLoaded(false);
      setPaymentError('');
      try {
        const [feeData, termData, attendanceData] = await Promise.all([
          api('/portal/parent/children/' + selectedId + '/fee-status'),
          api('/portal/parent/children/' + selectedId + '/terms'),
          api('/portal/parent/children/' + selectedId + '/attendance'),
        ]);
        if (active) {
          setFees(feeData);
          setAttendance(attendanceData);
          const availableTerms = termData.terms || [];
          setTerms(availableTerms);
          setSelectedTermId(availableTerms.length ? String(availableTerms[0].id) : '');
          setTermsLoaded(true);
        }
      } catch (err) {
        if (active) {
          setError(err.message);
          setTermsLoaded(true);
        }
      }
    }
    loadChild();
    return () => { active = false; };
  }, [selectedId]);

  useEffect(() => {
    let active = true;
    async function loadResults() {
      if (!selectedId || !termsLoaded) return;
      setResults(null);
      try {
        const query = selectedTermId ? '?term_id=' + encodeURIComponent(selectedTermId) : '';
        const resultData = await api('/portal/parent/children/' + selectedId + '/report-card' + query);
        if (active) setResults(resultData);
      } catch (err) {
        if (active) setError(err.message);
      }
    }
    loadResults();
    return () => { active = false; };
  }, [selectedId, selectedTermId, termsLoaded]);


  useEffect(() => {
    let active = true;
    async function loadCommunications() {
      if (!selectedId) {
        setTeachers([]); setConversations([]); setSelectedConversationId(''); setMessages([]);
        return;
      }
      try {
        const [teacherData, conversationData] = await Promise.all([
          api('/communications/teachers?student_id=' + encodeURIComponent(selectedId)),
          api('/communications/conversations'),
        ]);
        if (!active) return;
        setTeachers(teacherData.teachers || []);
        setSelectedTeacherId(teacherData.teachers?.length ? String(teacherData.teachers[0].id) : '');
        const rows = conversationData.conversations || [];
        const forChild = rows.filter(row => String(row.student_id) === String(selectedId));
        setConversations(forChild);
        setSelectedConversationId(forChild.length ? String(forChild[0].id) : '');
      } catch (err) {
        if (active) setError(err.message || 'Unable to load school communications.');
      }
    }
    loadCommunications();
    return () => { active = false; };
  }, [selectedId]);

  useEffect(() => {
    let active = true;
    async function loadMessages() {
      if (!selectedConversationId) { setMessages([]); return; }
      try {
        const data = await api('/communications/conversations/' + selectedConversationId + '/messages');
        if (active) setMessages(data.messages || []);
      } catch (err) { if (active) setError(err.message || 'Unable to load messages.'); }
    }
    loadMessages();
    return () => { active = false; };
  }, [selectedConversationId]);

  async function startConversation(event) {
    event.preventDefault();
    if (!selectedId || !selectedTeacherId || !messageSubject.trim()) return;
    setSendingMessage(true); setError('');
    try {
      const created = await api('/communications/conversations', { method: 'POST', body: JSON.stringify({
        student_id: Number(selectedId), teacher_user_id: Number(selectedTeacherId), subject: messageSubject.trim(),
      }) });
      const data = await api('/communications/conversations');
      const rows = (data.conversations || []).filter(row => String(row.student_id) === String(selectedId));
      setConversations(rows);
      setSelectedConversationId(String(created.id));
      setMessageSubject('');
    } catch (err) { setError(err.message || 'Unable to start conversation.'); }
    finally { setSendingMessage(false); }
  }

  async function sendParentMessage(event) {
    event.preventDefault();
    if (!selectedConversationId || !messageDraft.trim() || sendingMessage) return;
    setSendingMessage(true); setError('');
    try {
      await api('/communications/conversations/' + selectedConversationId + '/messages', {
        method: 'POST', body: JSON.stringify({ body: messageDraft.trim() }),
      });
      const data = await api('/communications/conversations/' + selectedConversationId + '/messages');
      setMessages(data.messages || []);
      setMessageDraft('');
    } catch (err) { setError(err.message || 'Message could not be sent.'); }
    finally { setSendingMessage(false); }
  }

  async function payFees() {
    if (!selectedId || paying || !fees || Number(fees.total_balance) <= 0) return;
    setPaying(true);
    setPaymentError('');
    try {
      const response = await api('/paynow/initiate', { method: 'POST', body: JSON.stringify({ student_id: Number(selectedId) }) });
      if (!response.browser_url) throw new Error('The payment provider did not return a secure checkout link. Please try again or contact the school.');
      window.location.href = response.browser_url;
    } catch (err) {
      setPaymentError(err.message || 'Unable to start your payment. Please try again.');
      setPaying(false);
    }
  }

  async function logout() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  if (loading) return <main className="container"><section className="card" role="status">Loading your parent portal…</section></main>;

  return (
    <main className="container" style={{ maxWidth: 1000, margin: '2rem auto', padding: '0 1rem' }}>
      <section className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <div><p style={{ margin: 0, opacity: .7 }}>CHIKORO DIGITAL · FAMILY PORTAL</p><h1 style={{ margin: '8px 0' }}>Parent dashboard</h1><p style={{ margin: 0 }}>View information for learners verified and linked to your account.</p></div>
          <button type="button" onClick={logout}>Log out</button>
        </div>
        {error && <p role="alert" style={{ color: '#b42318', marginTop: 18 }}>{error}</p>}
        {!children.length && <div style={{ marginTop: 24 }}><h2>No linked learners yet</h2><p>Your school must verify and activate your guardian relationship before learner information appears here. Please contact the school office.</p></div>}
        {!!children.length && <div style={{ marginTop: 24 }}>
          <label htmlFor="parent-child" style={{ display: 'block', fontWeight: 600, marginBottom: 8 }}>Select learner</label>
          <select id="parent-child" value={selectedId} onChange={event => setSelectedId(event.target.value)} style={{ width: '100%', maxWidth: 420, padding: 12, borderRadius: 8 }}>
            {children.map(child => <option key={child.id} value={child.id}>{child.name} · {child.student_number}{child.form ? ' · ' + child.form : ''}</option>)}
          </select>
          {!!terms.length && <div style={{ marginTop: 16 }}>
            <label htmlFor="parent-term" style={{ display: 'block', fontWeight: 600, marginBottom: 8 }}>Report-card term</label>
            <select id="parent-term" value={selectedTermId} onChange={event => setSelectedTermId(event.target.value)} style={{ width: '100%', maxWidth: 420, padding: 12, borderRadius: 8 }}>
              {terms.map(term => <option key={term.id} value={String(term.id)}>{term.name} · {term.academic_year}{term.is_current ? ' · Current' : ''}</option>)}
            </select>
          </div>}
        </div>}
      </section>

      {fees && <section className="card" style={{ marginTop: 18 }}>
        <h2>Fee statement</h2>
        <p><strong>{fees.name}</strong> · {fees.student_number}</p>
        <p style={{ fontSize: 22, fontWeight: 700 }}>Outstanding USD balance: {Number(fees.total_balance).toFixed(2)} USD</p>
        {Object.entries(fees.balances_by_currency || {}).filter(([currency]) => currency !== 'USD').map(([currency, balance]) => <p key={currency}>Outstanding {currency} balance: {Number(balance).toFixed(2)}</p>)}
        <button type="button" onClick={payFees} disabled={paying || Number(fees.total_balance) <= 0}>{paying ? 'Opening secure checkout…' : 'Pay USD balance securely'}</button>
        {paymentError && <p role="alert" style={{ color: '#b42318', marginTop: 10 }}>{paymentError}</p>}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr><th align="left">Invoice</th><th align="right">Total</th><th align="right">Balance</th></tr></thead>
            <tbody>{fees.invoices.map(invoice => <tr key={invoice.invoice_number}><td>{invoice.invoice_number}</td><td align="right">{Number(invoice.total).toFixed(2)} {invoice.currency}</td><td align="right">{Number(invoice.balance).toFixed(2)} {invoice.currency}</td></tr>)}</tbody>
          </table>
        </div>
      </section>}

      {attendance && <section className="card" style={{ marginTop: 18 }}>
        <h2>Attendance summary</h2>
        <p style={{ color: '#64748b' }}>Based on submitted class registers only. Draft registers are not visible to parents.</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(125px, 1fr))', gap: 12, margin: '16px 0' }}>
          <div><strong style={{ display: 'block', fontSize: 24 }}>{attendance.summary.attendance_rate == null ? '—' : attendance.summary.attendance_rate + '%'}</strong><span>Attendance rate</span></div>
          <div><strong style={{ display: 'block', fontSize: 24 }}>{attendance.summary.present}</strong><span>Present</span></div>
          <div><strong style={{ display: 'block', fontSize: 24 }}>{attendance.summary.absent}</strong><span>Absent</span></div>
          <div><strong style={{ display: 'block', fontSize: 24 }}>{attendance.summary.late}</strong><span>Late</span></div>
          <div><strong style={{ display: 'block', fontSize: 24 }}>{attendance.summary.excused}</strong><span>Excused</span></div>
        </div>
        {!attendance.records.length ? <p>No submitted attendance records are available yet.</p> : <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr><th align="left">Date</th><th align="left">Class</th><th align="left">Status</th><th align="left">Note</th></tr></thead>
            <tbody>{attendance.records.map((record, index) => <tr key={record.date + '-' + index}><td>{record.date}</td><td>{record.class_name}</td><td style={{ textTransform: 'capitalize' }}>{record.status}</td><td>{record.note || '—'}</td></tr>)}</tbody>
          </table>
          {attendance.records_limited && <p style={{ color: '#64748b' }}>Showing the latest 100 records.</p>}
        </div>}
      </section>}

      {!!children.length && <section className="card" style={{ marginTop: 18 }}>
        <h2>Message your child's teacher</h2>
        <p style={{ color: '#64748b' }}>Only teachers currently assigned to this learner's class are available. Messages remain inside the secure school portal.</p>
        <form onSubmit={startConversation} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, marginBottom: 16 }}>
          <label>Assigned teacher
            <select value={selectedTeacherId} onChange={e => setSelectedTeacherId(e.target.value)} required disabled={!teachers.length} style={{ display: 'block', width: '100%', padding: 10, marginTop: 5 }}>
              {teachers.map(teacher => <option key={teacher.id} value={teacher.id}>{teacher.name}</option>)}
            </select>
          </label>
          <label>Conversation subject
            <input value={messageSubject} onChange={e => setMessageSubject(e.target.value)} required maxLength={160} placeholder="e.g. Homework support" style={{ display: 'block', width: '100%', boxSizing: 'border-box', padding: 10, marginTop: 5 }} />
          </label>
          <div style={{ alignSelf: 'end' }}><button type="submit" disabled={sendingMessage || !teachers.length}>{sendingMessage ? 'Starting…' : 'Start conversation'}</button></div>
        </form>
        {!teachers.length && <p>No class teacher is currently assigned to this learner. Please contact the school office.</p>}
        {!!conversations.length && <label style={{ display: 'block', marginBottom: 10 }}>Your conversations
          <select value={selectedConversationId} onChange={e => setSelectedConversationId(e.target.value)} style={{ display: 'block', width: '100%', maxWidth: 500, padding: 10, marginTop: 5 }}>
            {conversations.map(row => <option key={row.id} value={row.id}>{row.subject} · {row.teacher_name} · {row.status}</option>)}
          </select>
        </label>}
        {selectedConversationId && <div style={{ border: '1px solid #e2e8f0', borderRadius: 10, padding: 12 }}>
          <div style={{ maxHeight: 300, overflowY: 'auto' }}>
            {messages.map(message => <div key={message.id} style={{ padding: 10, margin: '8px 0', borderRadius: 8, background: message.is_mine ? '#eff6ff' : '#f8fafc' }}>
              <strong>{message.is_mine ? 'You' : 'Teacher'}</strong><p style={{ whiteSpace: 'pre-wrap', margin: '5px 0' }}>{message.body}</p><small style={{ color: '#64748b' }}>{new Date(message.created_at).toLocaleString()}</small>
            </div>)}
            {!messages.length && <p>No messages yet. Send the first message below.</p>}
          </div>
          <form onSubmit={sendParentMessage} style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            <textarea value={messageDraft} onChange={e => setMessageDraft(e.target.value)} required maxLength={5000} rows={3} placeholder="Write a message…" style={{ flex: '1 1 260px', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }} />
            <button type="submit" disabled={sendingMessage || !messageDraft.trim()}>{sendingMessage ? 'Sending…' : 'Send message'}</button>
          </form>
        </div>}
      </section>}

      {results && <section className="card" style={{ marginTop: 18 }}>
        <h2>Published results</h2>
        {!results.subjects.length && <p>No results have been published for this learner yet.</p>}
        {results.subjects.map(subject => <div key={subject.subject} style={{ borderTop: '1px solid #e5e7eb', padding: '12px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><strong>{subject.subject}</strong><strong>{Number(subject.average).toFixed(1)}%</strong></div>
          <ul>{subject.assessments.map(item => <li key={item.name}>{item.name}: {item.score} / {item.max}</li>)}</ul>
        </div>)}
      </section>}
    </main>
  );
}
