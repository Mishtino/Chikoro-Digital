import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function PortalFees() {
  const router = useRouter();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [paying, setPaying] = useState(false);

  useEffect(() => {
    let active = true;
    getSupabaseBrowserClient().auth.getSession().then(({ data: { session } }) => {
      if (!session) { router.replace('/portal/login'); return; }
      api('/portal/fee-status').then((result) => { if (active) setData(result); })
        .catch((e) => { if (active) setError(e.message); });
    }).catch(() => router.replace('/portal/login'));
    return () => { active = false; };
  }, [router]);

  async function pay() {
    setPaying(true);
    setError('');
    try {
      const res = await api('/paynow/initiate', { method: 'POST', body: JSON.stringify({}) });
      if (res.browser_url) window.location.href = res.browser_url;
    } catch (e) {
      setError(e.message);
      setPaying(false);
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
        <h1>Fee statement</h1>
        <p>{data.name} · {data.student_number}</p>
        <h2>Total outstanding: {Number(data.total_balance).toFixed(2)} USD</h2>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="auth-submit" onClick={pay} disabled={paying}>{paying ? 'Connecting to Paynow…' : 'Pay outstanding balance'}</button>
        <table>
          <thead><tr><th>Invoice</th><th>Total</th><th>Balance</th></tr></thead>
          <tbody>{data.invoices.map((inv) => <tr key={inv.invoice_number}><td>{inv.invoice_number}</td><td>{Number(inv.total).toFixed(2)} {inv.currency}</td><td>{Number(inv.balance).toFixed(2)} {inv.currency}</td></tr>)}</tbody>
        </table>
        <p><button type="button" className="auth-submit" onClick={logout}>Sign out</button></p>
      </section>
    </main>
  );
}
