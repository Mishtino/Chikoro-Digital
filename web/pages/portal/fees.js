import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';

export default function PortalFees() {
  const router = useRouter();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!localStorage.getItem('token')) { router.push('/portal/login'); return; }
    api('/portal/fee-status').then(setData).catch((e) => setError(e.message));
  }, [router]);
  async function pay() {
    try {
      const res = await api('/paynow/initiate', { method: 'POST', body: JSON.stringify({}) });
      if (res.browser_url) window.location.href = res.browser_url;
    } catch (e) {
      setError(e.message);
    }
  }
  if (!data) return <div className="container"><div className="card">Loading...</div></div>;
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
        <p style={{ marginTop: '1rem' }}><a href="#" onClick={() => { localStorage.removeItem('token'); router.push('/'); }}>Log out</a></p>
      </div>
    </div>
  );
}
