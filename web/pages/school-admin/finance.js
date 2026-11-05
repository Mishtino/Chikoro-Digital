import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function SchoolFinance() {
  const router = useRouter();
  const [role, setRole] = useState('');
  const [students, setStudents] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [payments, setPayments] = useState([]);
  const [form, setForm] = useState({ student_id: '', amount: '', currency: 'USD', method: 'cash', reference: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function refresh() {
    const [studentRows, invoiceRows, paymentRows] = await Promise.all([
      api('/students'), api('/invoices'), api('/payments'),
    ]);
    setStudents(Array.isArray(studentRows) ? studentRows : []);
    setInvoices(Array.isArray(invoiceRows) ? invoiceRows : []);
    setPayments(Array.isArray(paymentRows) ? paymentRows : []);
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError || !data.session?.access_token) { router.replace('/portal/login'); return; }
        const profile = await api('/auth/supabase/me');
        if (!['owner', 'headmaster', 'bursar'].includes(profile.role) || profile.is_admin || !profile.school_id) {
          await supabase.auth.signOut();
          router.replace('/portal/login');
          return;
        }
        const [studentRows, invoiceRows, paymentRows] = await Promise.all([
          api('/students'), api('/invoices'), api('/payments'),
        ]);
        if (!active) return;
        setRole(profile.role);
        setStudents(Array.isArray(studentRows) ? studentRows : []);
        setInvoices(Array.isArray(invoiceRows) ? invoiceRows : []);
        setPayments(Array.isArray(paymentRows) ? paymentRows : []);
      } catch (e) {
        if (active) setError(e.message || 'Unable to load school finance records.');
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, [router]);

  const studentById = useMemo(() => new Map(students.map(student => [student.id, student])), [students]);
  const totals = useMemo(() => invoices.reduce((acc, invoice) => {
    if (invoice.status !== 'void' && Number(invoice.balance) > 0) {
      const currency = invoice.currency || 'USD';
      acc[currency] = (acc[currency] || 0) + Number(invoice.balance);
    }
    return acc;
  }, {}), [invoices]);

  async function recordPayment(event) {
    event.preventDefault();
    setSaving(true); setError(''); setNotice('');
    try {
      const amount = Number(form.amount);
      if (!Number.isFinite(amount) || amount <= 0 || Math.round(amount * 100) !== amount * 100) {
        throw new Error('Enter a positive amount with no more than two decimal places.');
      }
      const result = await api('/payments', {
        method: 'POST',
        body: JSON.stringify({
          student_id: Number(form.student_id),
          amount: form.amount,
          currency: form.currency.trim().toUpperCase(),
          method: form.method,
          reference: form.reference.trim() || null,
        }),
      });
      setForm(current => ({ ...current, amount: '', reference: '' }));
      setNotice(`Payment recorded. Receipt number: ${result.receipt_number}`);
      await refresh();
    } catch (e) { setError(e.message || 'Payment could not be recorded.'); }
    finally { setSaving(false); }
  }

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  const outstandingInvoices = invoices.filter(invoice => invoice.status !== 'void' && Number(invoice.balance) > 0);

  return <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '30px 18px', color: '#172033' }}>
    <div style={{ maxWidth: 1120, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 24 }}>
        <div><p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>CHIKORO DIGITAL · SCHOOL FINANCE</p><h1 style={{ margin: '7px 0 4px' }}>Fees & payments</h1><p style={{ margin: 0, color: '#64748b' }}>Signed in as {role.replaceAll('_', ' ')}</p></div>
        <div style={{ display: 'flex', gap: 9 }}>{['owner', 'headmaster'].includes(role) && <Link href="/school-admin" style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', textDecoration: 'none', color: '#172033', background: '#fff' }}>Dashboard</Link>}<button onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', background: '#fff', cursor: 'pointer' }}>Sign out</button></div>
      </header>
      {error && <p role="alert" style={{ padding: 12, borderRadius: 8, background: '#fff1f0', color: '#b42318' }}>{error}</p>}
      {notice && <p role="status" style={{ padding: 12, borderRadius: 8, background: '#ecfdf3', color: '#067647' }}>{notice}</p>}
      {loading ? <p role="status">Loading finance records…</p> : !error && <>
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 18 }}>
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 17 }}><p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>Open invoices</p><strong style={{ fontSize: 27 }}>{outstandingInvoices.length}</strong></article>
          {Object.entries(totals).map(([currency, amount]) => <article key={currency} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 17 }}><p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>Outstanding · {currency}</p><strong style={{ fontSize: 27 }}>{amount.toFixed(2)}</strong></article>)}
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 17 }}><p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>Recorded payments</p><strong style={{ fontSize: 27 }}>{payments.length}</strong></article>
        </section>

        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22, marginBottom: 18 }}>
          <h2 style={{ margin: '0 0 5px', fontSize: 19 }}>Record a payment</h2>
          <p style={{ margin: '0 0 16px', color: '#64748b', fontSize: 13 }}>Payments are allocated against the learner's oldest eligible invoices. The API rejects overpayments and duplicate references.</p>
          <form onSubmit={recordPayment} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, alignItems: 'end' }}>
            <div><label htmlFor="payment-student" style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Learner</label><select id="payment-student" required value={form.student_id} onChange={e => setForm(current => ({ ...current, student_id: e.target.value }))} style={{ width: '100%', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}><option value="">Select learner</option>{students.filter(student => student.status === 'active').map(student => <option key={student.id} value={student.id}>{student.student_number} · {student.first_name} {student.last_name}</option>)}</select></div>
            <div><label htmlFor="payment-amount" style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Amount</label><input id="payment-amount" type="number" min="0.01" step="0.01" required value={form.amount} onChange={e => setForm(current => ({ ...current, amount: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <div><label htmlFor="payment-currency" style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Currency</label><input id="payment-currency" required minLength={3} maxLength={3} value={form.currency} onChange={e => setForm(current => ({ ...current, currency: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, textTransform: 'uppercase' }} /></div>
            <div><label htmlFor="payment-method" style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Method</label><select id="payment-method" value={form.method} onChange={e => setForm(current => ({ ...current, method: e.target.value }))} style={{ width: '100%', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}><option value="cash">Cash</option><option value="bank">Bank transfer</option><option value="mobile">Mobile money</option></select></div>
            <div><label htmlFor="payment-reference" style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Reference (optional)</label><input id="payment-reference" maxLength={120} value={form.reference} onChange={e => setForm(current => ({ ...current, reference: e.target.value }))} style={{ width: '100%', boxSizing: 'border-box', padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }} /></div>
            <button type="submit" disabled={saving || !students.length} style={{ border: 0, borderRadius: 8, background: '#2457c5', color: '#fff', padding: 12, fontWeight: 600, cursor: saving ? 'wait' : 'pointer' }}>{saving ? 'Recording…' : 'Record payment'}</button>
          </form>
        </section>

        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22, marginBottom: 18 }}>
          <h2 style={{ margin: '0 0 14px', fontSize: 19 }}>Outstanding invoices</h2>
          {outstandingInvoices.length === 0 ? <p style={{ color: '#64748b' }}>No outstanding invoices found.</p> : <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: 650 }}>
            <thead><tr>{['Invoice', 'Learner', 'Total', 'Paid', 'Balance', 'Status'].map(label => <th key={label} style={{ padding: 10, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12 }}>{label}</th>)}</tr></thead>
            <tbody>{outstandingInvoices.map(invoice => { const student = studentById.get(invoice.student_id); return <tr key={invoice.id}><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{invoice.invoice_number}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{student ? `${student.first_name} ${student.last_name}` : `Learner #${invoice.student_id}`}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{invoice.currency} {Number(invoice.total).toFixed(2)}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{Number(invoice.paid).toFixed(2)}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5', fontWeight: 700 }}>{invoice.currency} {Number(invoice.balance).toFixed(2)}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{invoice.status}</td></tr>; })}</tbody>
          </table></div>}
        </section>

        <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22 }}>
          <h2 style={{ margin: '0 0 14px', fontSize: 19 }}>Recent payments</h2>
          {payments.length === 0 ? <p style={{ color: '#64748b' }}>No payments recorded yet.</p> : <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: 600 }}>
            <thead><tr>{['Date', 'Learner', 'Amount', 'Method', 'Reference', 'Status'].map(label => <th key={label} style={{ padding: 10, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12 }}>{label}</th>)}</tr></thead>
            <tbody>{payments.slice(0, 30).map(payment => { const student = studentById.get(payment.student_id); return <tr key={payment.id}><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{payment.received_at ? new Date(payment.received_at).toLocaleDateString() : '—'}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{student ? `${student.first_name} ${student.last_name}` : `Learner #${payment.student_id}`}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{payment.currency} {Number(payment.amount).toFixed(2)}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{payment.method}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{payment.reference || '—'}</td><td style={{ padding: 10, borderBottom: '1px solid #edf1f5' }}>{payment.voided ? 'Voided' : 'Recorded'}</td></tr>; })}</tbody>
          </table></div>}
        </section>
      </>}
    </div>
  </main>;
}
