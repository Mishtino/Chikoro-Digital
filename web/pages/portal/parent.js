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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
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
        return;
      }
      setError('');
      setFees(null);
      setResults(null);
      try {
        const [feeData, resultData] = await Promise.all([
          api('/portal/parent/children/' + selectedId + '/fee-status'),
          api('/portal/parent/children/' + selectedId + '/report-card'),
        ]);
        if (active) {
          setFees(feeData);
          setResults(resultData);
        }
      } catch (err) {
        if (active) setError(err.message);
      }
    }
    loadChild();
    return () => { active = false; };
  }, [selectedId]);

  async function payFees() {
    if (!selectedId) return;
    setPaying(true);
    setError('');
    try {
      const response = await api('/paynow/initiate', { method: 'POST', body: JSON.stringify({ student_id: Number(selectedId) }) });
      if (!response.browser_url) throw new Error('The payment provider did not return a checkout link.');
      window.location.href = response.browser_url;
    } catch (err) {
      setError(err.message);
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
        </div>}
      </section>

      {fees && <section className="card" style={{ marginTop: 18 }}>
        <h2>Fee statement</h2>
        <p><strong>{fees.name}</strong> · {fees.student_number}</p>
        <p style={{ fontSize: 22, fontWeight: 700 }}>Outstanding USD balance: {Number(fees.total_balance).toFixed(2)} USD</p>
        {Object.entries(fees.balances_by_currency || {}).filter(([currency]) => currency !== 'USD').map(([currency, balance]) => <p key={currency}>Outstanding {currency} balance: {Number(balance).toFixed(2)}</p>)}
        <button type="button" onClick={payFees} disabled={paying || Number(fees.total_balance) <= 0}>{paying ? 'Opening secure checkout…' : 'Pay fees securely'}</button>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr><th align="left">Invoice</th><th align="right">Total</th><th align="right">Balance</th></tr></thead>
            <tbody>{fees.invoices.map(invoice => <tr key={invoice.invoice_number}><td>{invoice.invoice_number}</td><td align="right">{Number(invoice.total).toFixed(2)} {invoice.currency}</td><td align="right">{Number(invoice.balance).toFixed(2)} {invoice.currency}</td></tr>)}</tbody>
          </table>
        </div>
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
