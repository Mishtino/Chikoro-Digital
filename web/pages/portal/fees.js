import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function PortalFees() {
  const router = useRouter();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    getSupabaseBrowserClient().auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return;
      if (sessionError || !data.session) { router.push('/portal/login'); return; }
      api('/portal/fee-status').then((result) => { if (active) setData(result); }).catch((e) => { if (active) setError(e.message); });
    }).catch(() => router.push('/portal/login'));
    return () => { active = false; };
  }, [router]);
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
        <p><strong>Total balance: {data.total_balance.toFixed(2)} USD</strong></p>
        <button onClick={pay} style={{ marginBottom: '1rem' }}>Pay now</button>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr><th align="left">Invoice</th><th align="right">Total</th><th align="right">Balance</th></tr></thead>
          <tbody>
            {data.invoices.map((inv) => (
              <tr key={inv.invoice_number}>
                <td>{inv.invoice_number}</td>
                <td align="right">{inv.total.toFixed(2)}</td>
                <td align="right">{inv.balance.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p style={{ marginTop: '1rem' }}><a href="#" onClick={async (event) => { event.preventDefault(); await getSupabaseBrowserClient().auth.signOut(); router.push('/portal/login'); }}>Log out</a></p>
      </div>
    </div>
  );
}
