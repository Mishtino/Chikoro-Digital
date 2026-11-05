import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { api } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase';

const initial = {
  school: null,
  students: { total: 0, active: 0, inactive: 0 },
  staff: { active: 0, disabled: 0 },
  academics: { current_term: null, subjects: 0, assessments: 0, marks: { draft: 0, approved: 0, published: 0 } },
  finance: { open_invoices: 0, outstanding_by_currency: {} },
};

function Metric({ label, value, detail }) {
  return <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20 }}>
    <p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>{label}</p>
    <strong style={{ display: 'block', fontSize: 30, marginTop: 8, color: '#172033' }}>{value}</strong>
    {detail && <p style={{ margin: '5px 0 0', color: '#64748b', fontSize: 13 }}>{detail}</p>}
  </article>;
}

export default function SchoolAdminDashboard() {
  const router = useRouter();
  const [overview, setOverview] = useState(initial);
  const [role, setRole] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError || !data.session?.access_token) {
          router.replace('/portal/login');
          return;
        }
        const profile = await api('/auth/supabase/me');
        if (!['owner', 'headmaster'].includes(profile.role) || profile.is_admin || !profile.school_id) {
          await supabase.auth.signOut();
          router.replace('/portal/login');
          return;
        }
        const dataOverview = await api('/school-admin/overview');
        if (!active) return;
        setRole(profile.role);
        setOverview(dataOverview);
      } catch (e) {
        if (active) setError(e.message || 'Unable to load the school dashboard.');
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, [router]);

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  const outstanding = Object.entries(overview.finance?.outstanding_by_currency || {});
  const school = overview.school;

  return <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '32px 18px', color: '#172033' }}>
    <div style={{ maxWidth: 1120, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 28 }}>
        <div>
          <p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>CHIKORO DIGITAL · SCHOOL ADMINISTRATION</p>
          <h1 style={{ margin: '8px 0 4px' }}>{school?.name || 'School dashboard'}</h1>
          <p style={{ margin: 0, color: '#64748b' }}>{school ? `${school.code} · ${school.province || 'Province not set'} · ${school.status}` : 'Your school overview'} {role ? `· ${role.replaceAll('_', ' ')}` : ''}</p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Link href="/school-admin/staff" style={{ background: '#2457c5', color: '#fff', textDecoration: 'none', borderRadius: 8, padding: '11px 15px', fontWeight: 600 }}>Manage staff</Link>
          <button type="button" onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff', padding: '10px 14px', cursor: 'pointer' }}>Sign out</button>
        </div>
      </header>

      {error && <p role="alert" style={{ padding: 14, borderRadius: 9, background: '#fff1f0', color: '#b42318' }}>{error}</p>}
      {loading ? <p role="status">Loading your school overview…</p> : !error && <>
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14, marginBottom: 22 }}>
          <Metric label="Total learners" value={overview.students.total} detail={`${overview.students.active} active · ${overview.students.inactive} inactive`} />
          <Metric label="Active staff" value={overview.staff.active} detail={`${overview.staff.disabled} disabled accounts`} />
          <Metric label="Subjects" value={overview.academics.subjects} detail={`${overview.academics.assessments} assessments`} />
          <Metric label="Open invoices" value={overview.finance.open_invoices} detail="Invoices with an outstanding balance" />
        </section>

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22 }}>
            <h2 style={{ margin: '0 0 14px', fontSize: 18 }}>Academic term</h2>
            {overview.academics.current_term ? <><strong>{overview.academics.current_term.name}</strong><p style={{ color: '#64748b', margin: '5px 0 0' }}>{overview.academics.current_term.academic_year}</p></> : <p style={{ color: '#64748b' }}>No current term has been configured yet.</p>}
            <div style={{ borderTop: '1px solid #edf1f5', marginTop: 18, paddingTop: 14, color: '#64748b', fontSize: 14 }}>
              Marks: {overview.academics.marks.draft} draft · {overview.academics.marks.approved} approved · {overview.academics.marks.published} published
            </div>
          </article>
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22 }}>
            <h2 style={{ margin: '0 0 14px', fontSize: 18 }}>Outstanding fees</h2>
            {outstanding.length ? outstanding.map(([currency, amount]) => <p key={currency} style={{ display: 'flex', justifyContent: 'space-between', margin: '8px 0' }}><span style={{ color: '#64748b' }}>{currency}</span><strong>{amount}</strong></p>) : <p style={{ color: '#64748b' }}>No outstanding invoice balances recorded.</p>}
            <p style={{ margin: '15px 0 0', color: '#64748b', fontSize: 13 }}>Balances exclude void invoices and voided payments.</p>
          </article>
          <article style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 22 }}>
            <h2 style={{ margin: '0 0 14px', fontSize: 18 }}>Administration</h2>
            <Link href="/school-admin/staff" style={{ display: 'block', color: '#2457c5', fontWeight: 600, marginBottom: 10 }}>Open staff directory →</Link>
            <Link href="/school-admin/students" style={{ display: 'block', color: '#2457c5', fontWeight: 600, marginBottom: 10 }}>Manage learners →</Link>
            <Link href="/school-admin/finance" style={{ display: 'block', color: '#2457c5', fontWeight: 600, marginBottom: 10 }}>Fees & payments →</Link>
            <Link href="/school-admin/academics" style={{ display: 'block', color: '#2457c5', fontWeight: 600, marginBottom: 10 }}>Terms & results →</Link>
            <p style={{ color: '#64748b', fontSize: 14, lineHeight: 1.6, margin: 0 }}>Manage school staff access from one place. Timetable, attendance and detailed finance screens are being developed as separate modules.</p>
          </article>
        </section>
      </>}
      <footer style={{ marginTop: 28, color: '#94a3b8', fontSize: 12 }}>Chikoro Digital · School-scoped administration</footer>
    </div>
  </main>;
}
