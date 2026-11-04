import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function PortalFees() {
  const router = useRouter();
  const [data, setData] = useState(null);
  const [results, setResults] = useState(null);
  const [terms, setTerms] = useState([]);
  const [selectedTermId, setSelectedTermId] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    getSupabaseBrowserClient().auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return;
      if (sessionError || !data.session) { router.push('/portal/login'); return; }
      Promise.all([api('/portal/fee-status'), api('/portal/terms')]).then(([feeData, termData]) => {
        if (active) {
          setData(feeData);
          const availableTerms = termData.terms || [];
          setTerms(availableTerms);
          setSelectedTermId(availableTerms.length ? String(availableTerms[0].id) : '');
        }
      }).catch((e) => { if (active) setError(e.message); });
    }).catch(() => router.push('/portal/login'));
    return () => { active = false; };
  }, [router]);
  useEffect(() => {
    let active = true;
    if (!selectedTermId) {
      setResults(null);
      return () => { active = false; };
    }
    api('/portal/results?term_id=' + encodeURIComponent(selectedTermId))
      .then(resultData => { if (active) setResults(resultData); })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [selectedTermId]);

  async function pay() {
    try {
      const res = await api('/paynow/initiate', { method: 'POST', body: JSON.stringify({}) });
      if (res.browser_url) window.location.href = res.browser_url;
    } catch (e) {
      setError(e.message);
    }
  }
  if (error) return <div className="container"><div className="card"><h1>Unable to load your fee statement</h1><p role="alert">{error}</p><button onClick={() => router.push('/portal/login')}>Return to sign in</button></div></div>;
  if (!data) return <div className="container"><div className="card" role="status">Loading your secure fee statement…</div></div>;
  return (
    <div className="container">
      <div className="card">
        <h1>Fee status</h1>
        <p>{data.name} ({data.student_number})</p>
        <p><strong>Outstanding USD balance: {data.total_balance.toFixed(2)} USD</strong></p>
        {Object.entries(data.balances_by_currency || {}).filter(([currency]) => currency !== 'USD').map(([currency, balance]) => <p key={currency}>Outstanding {currency} balance: {Number(balance).toFixed(2)}</p>)}
        <button onClick={pay} disabled={data.total_balance <= 0} style={{ marginBottom: '1rem' }}>Pay now</button>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr><th align="left">Invoice</th><th align="right">Total</th><th align="right">Balance</th><th align="right">Currency</th></tr></thead>
          <tbody>
            {data.invoices.map((inv) => (
              <tr key={inv.invoice_number}>
                <td>{inv.invoice_number}</td>
                <td align="right">{inv.total.toFixed(2)}</td>
                <td align="right">{inv.balance.toFixed(2)}</td><td align="right">{inv.currency}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!!terms.length && <div style={{ marginTop: '2rem' }}>
          <label htmlFor="student-term" style={{ display: 'block', fontWeight: 600, marginBottom: 8 }}>Report-card term</label>
          <select id="student-term" value={selectedTermId} onChange={event => setSelectedTermId(event.target.value)} style={{ width: '100%', maxWidth: 420, padding: 12, borderRadius: 8 }}>
            {terms.map(term => <option key={term.id} value={String(term.id)}>{term.name} · {term.academic_year}{term.is_current ? ' · Current' : ''}</option>)}
          </select>
        </div>}
        {results && <section style={{ marginTop: '2rem' }}><h2>Published results</h2>{!results.subjects.length && <p>No results have been published yet.</p>}{results.subjects.map(subject => <div key={subject.subject} style={{ borderTop: '1px solid #e5e7eb', padding: '12px 0' }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><strong>{subject.subject}</strong><strong>{subject.average.toFixed(1)}%</strong></div><ul>{subject.assessments.map(item => <li key={item.name}>{item.name}: {item.score} / {item.max}</li>)}</ul></div>)}</section>}
        <p style={{ marginTop: '1rem' }}><a href="#" onClick={async (event) => { event.preventDefault(); await getSupabaseBrowserClient().auth.signOut(); router.push('/portal/login'); }}>Log out</a></p>
      </div>
    </div>
  );
}
