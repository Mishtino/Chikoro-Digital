import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { api } from '../../lib/api';
import Brand from '../../components/Brand';
import { getSupabaseBrowserClient } from '../../lib/supabase';

export default function AcademicAnalytics() {
  const router = useRouter();
  const [terms, setTerms] = useState([]);
  const [termId, setTermId] = useState('current');
  const [rows, setRows] = useState([]);
  const [trends, setTrends] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function load(selectedTerm = termId) {
    setLoading(true); setError('');
    try {
      const query = selectedTerm && selectedTerm !== 'all' ? '?term_id=' + encodeURIComponent(selectedTerm) : '';
      const data = await api('/results/analytics/class-performance' + query);
      setRows(data.results || []);
    } catch (e) { setError(e.message || 'Unable to load class performance.'); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    let active = true;
    async function initialise() {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError || !data.session?.access_token) { router.replace('/portal/login'); return; }
        const profile = await api('/auth/supabase/me');
        if (!['owner', 'headmaster'].includes(profile.role) || profile.is_admin || !profile.school_id) {
          await supabase.auth.signOut(); router.replace('/portal/login'); return;
        }
        const termRows = await api('/fees/terms');
        if (!active) return;
        setTerms(termRows || []);
        const current = (termRows || []).find(term => term.is_current);
        const selected = current ? String(current.id) : 'all';
        setTermId(selected);
        const query = selected !== 'all' ? '?term_id=' + selected : '';
        const [result, trendResult] = await Promise.all([
          api('/results/analytics/class-performance' + query),
          api('/results/analytics/subject-trends'),
        ]);
        if (active) { setRows(result.results || []); setTrends(trendResult.trends || []); }
      } catch (e) { if (active) setError(e.message || 'Unable to load academic analytics.'); }
      finally { if (active) setLoading(false); }
    }
    initialise();
    return () => { active = false; };
  }, [router]);

  async function signOut() {
    await getSupabaseBrowserClient().auth.signOut();
    router.replace('/portal/login');
  }

  return <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '30px 18px', color: '#172033' }}>
    <div style={{ maxWidth: 1120, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 24 }}>
        <div><div style={{ marginBottom: 10 }}><Brand compact /></div><p style={{ margin: 0, color: '#53627a', fontSize: 13, fontWeight: 700, letterSpacing: '.08em' }}>SCHOOL WORKSPACE</p><h1 style={{ margin: '7px 0 4px' }}>Class performance</h1><p style={{ margin: 0, color: '#64748b' }}>Published results only · aggregated by class and subject.</p></div>
        <div style={{ display: 'flex', gap: 9 }}><Link href="/school-admin" style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', textDecoration: 'none', color: '#172033', background: '#fff' }}>Dashboard</Link><button onClick={signOut} style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: '10px 12px', background: '#fff', cursor: 'pointer' }}>Sign out</button></div>
      </header>
      {error && <p role="alert" style={{ padding: 12, background: '#fff1f0', color: '#b42318', borderRadius: 8 }}>{error}</p>}
      <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
          <div><h2 style={{ margin: 0, fontSize: 19 }}>Performance overview</h2><p style={{ color: '#64748b', margin: '5px 0 0', fontSize: 13 }}>Pass rate uses a 50% threshold. Draft and approved marks are excluded.</p></div>
          <div style={{ display: 'flex', gap: 8 }}><label htmlFor="analytics-term" style={{ alignSelf: 'center' }}>Term</label><select id="analytics-term" value={termId} onChange={e => { setTermId(e.target.value); load(e.target.value); }} style={{ padding: 9, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fff' }}><option value="all">All terms</option>{terms.map(term => <option key={term.id} value={term.id}>{term.name} · {term.academic_year}</option>)}</select></div>
        </div>
        {loading ? <p role="status">Loading performance data…</p> : rows.length === 0 ? <p style={{ color: '#64748b' }}>No published marks are available for this term.</p> : <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: 680 }}>
          <thead><tr>{['Class', 'Subject', 'Learners', 'Marks', 'Average', 'Pass rate'].map(label => <th key={label} style={{ padding: 11, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12 }}>{label}</th>)}</tr></thead>
          <tbody>{rows.map((row, index) => <tr key={row.class_name + '-' + row.subject_id + '-' + index}>
            <td style={{ padding: 11, borderBottom: '1px solid #edf1f5', fontWeight: 600 }}>{row.class_name || 'Unassigned'}</td>
            <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{row.subject_name}</td>
            <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{row.learner_count}</td>
            <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{row.mark_count}</td>
            <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{Number(row.average_percent).toFixed(1)}%</td>
            <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{row.pass_rate_percent == null ? '—' : Number(row.pass_rate_percent).toFixed(1) + '%'}</td>
          </tr>)}</tbody>
        </table></div>}
      </section>
      <section style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, padding: 20, marginTop: 18 }}>
        <h2 style={{ margin: 0, fontSize: 19 }}>Subject performance trends</h2>
        <p style={{ color: '#64748b', margin: '5px 0 14px', fontSize: 13 }}>Published marks across terms, grouped by subject and class.</p>
        {!trends.length ? <p style={{ color: '#64748b' }}>No published subject trends are available yet.</p> : <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: 680 }}>
            <thead><tr>{['Term', 'Class', 'Subject', 'Learners', 'Average', 'Pass rate'].map(label => <th key={label} style={{ padding: 11, borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: 12 }}>{label}</th>)}</tr></thead>
            <tbody>{trends.map((row, index) => <tr key={row.term_id + '-' + row.subject_id + '-' + row.class_name + '-' + index}>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{row.term_name} · {row.academic_year}</td>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{row.class_name || 'Unassigned'}</td>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{row.subject_name}</td>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{row.learner_count}</td>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{Number(row.average_percent).toFixed(1)}%</td>
              <td style={{ padding: 11, borderBottom: '1px solid #edf1f5' }}>{row.pass_rate_percent == null ? '—' : Number(row.pass_rate_percent).toFixed(1) + '%'}</td>
            </tr>)}</tbody>
          </table>
        </div>}
      </section>
    </div>
  </main>;
}
