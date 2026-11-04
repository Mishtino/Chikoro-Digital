import { useState } from 'react';
import { useRouter } from 'next/router';

export default function Home() {
  const [code,setCode]=useState(''); const router=useRouter();
  return <main className="portal-home"><section className="portal-home-card">
    <div className="brand-lockup"><span className="brand-mark">C</span><span>CHIKORO DIGITAL</span></div>
    <h1>Welcome to your school portal.</h1><p>Enter your school code to continue to the right student and parent portal. Your school code is available from your school office.</p>
    <form onSubmit={e=>{e.preventDefault();if(code.trim())router.push(`/portal/login?school=${encodeURIComponent(code.trim())}`);}}>
      <div className="field"><label htmlFor="home-school-code">School code</label><input id="home-school-code" value={code} onChange={e=>setCode(e.target.value)} placeholder="e.g. CHK001" required /></div>
      <button className="auth-button" type="submit">Continue to my school</button>
    </form>
    <p style={{fontSize:13,marginTop:24}}>School administrator? <a href="/admin/register">Administrator account setup</a></p>
  </section></main>;
}