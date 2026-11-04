import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function PortalFees() {
  const router = useRouter();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [payingStudent, setPayingStudent] = useState(null);

  useEffect(() => {
    let active = true;
    getSupabaseBrowserClient().auth.getSession().then(({ data: { session } }) => {
      if (!session) { router.replace('/portal/login'); return; }
      api('/portal/fee-status').then((result) => { if (active) setData(result); })
        .catch((e) => { if (active) setError(e.message); });
    }).catch(() => router.replace('/portal/login'));
    return () => { active = false; };
  }, [router]);

  async function pay(studentId) {
    setPayingStudent(studentId || 'student');
    setError('');
    try {
      const body = studentId ? { student_id: studentId } : {};
      const res = await api('/paynow/initiate', { method: 'POST', body: JSON.stringify(body) });
      if (res.browser_url) window.location.href = res.browser_url;
      else throw new Error('Paynow did not return a payment link.');
    } catch (e) {
      setError(e.message);
      setPayingStudent(null);
    }
  }

  async function logout() {
    await getSupabaseBrowserClient().auth.signOut();
    await router.replace('/portal/login');
  }

  if (error && !data) return <main className="container"><section className="card"><p className="error">{error}</p><button onClick={() => router.replace('/portal/login')}>Return to sign in</button></section></main>;
  if (!data) return <main className="container"><section className="card">Loading your secure fee statement…</section></main>;

  return (
    <main className="container">
      <section className="card">
        <p className="eyebrow">STUDENT & PARENT PORTAL</p>
        <h1>{data.role === 'parent' ? 'Family fee statements' : 'Fee statement'}</h1>
        <p>Welcome, {data.name}</p>
        {error && <p className="error" role="alert">{error}</p>}
        {data.role === 'parent' ? (
          <div className="guardian-children">
            {data.children.map((child) => (
              <section className="card" key={child.student_id}>
                <h2>{child.name}</h2>
                <p>Student number: {child.student_number}</p>
                <h3>Total outstanding: {Number(child.total_balance).toFixed(2)} USD</h3>
                <button className="auth-submit" onClick={() => pay(child.student_id)} disabled={!!payingStudent}>
                  {payingStudent === child.student_id ? 'Connecting to Paynow…' : 'Pay this learner’s balance'}
                </button>
                <table>
                  <thead><tr><th>Invoice</th><th>Total</th><th>Balance</th></tr></thead>
                  <tbody>{child.invoices.map((inv) => <tr key={inv.invoice_number}><td>{inv.invoice_number}</td><td>{Number(inv.total).toFixed(2)} {inv.currency}</td><td>{Number(inv.balance).toFixed(2)} {inv.currency}</td></tr>)}</tbody>
                </table>
              </section>
            ))}
          </div>
        ) : (
          <>
            <p>{data.name} · {data.student_number}</p>
            <h2>Total outstanding: {Number(data.total_balance).toFixed(2)} USD</h2>
            <button className="auth-submit" onClick={() => pay(null)} disabled={!!payingStudent}>{payingStudent ? 'Connecting to Paynow…' : 'Pay outstanding balance'}</button>
            <table>
              <thead><tr><th>Invoice</th><th>Total</th><th>Balance</th></tr></thead>
              <tbody>{data.invoices.map((inv) => <tr key={inv.invoice_number}><td>{inv.invoice_number}</td><td>{Number(inv.total).toFixed(2)} {inv.currency}</td><td>{Number(inv.balance).toFixed(2)} {inv.currency}</td></tr>)}</tbody>
            </table>
          </>
        )}
        <p><button type="button" className="auth-submit" onClick={logout}>Sign out</button></p>
      </section>
    </main>
  );
}
