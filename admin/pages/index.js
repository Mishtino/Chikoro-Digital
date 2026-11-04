import { useState } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseBrowserClient } from '../lib/supabase';
export default function AdminLogin() {
  const router=useRouter(); const [email,setEmail]=useState(''); const [password,setPassword]=useState(''); const [error,setError]=useState(''); const [loading,setLoading]=useState(false);
  async function submit(e){
    e.preventDefault();setError('');setLoading(true);
    try{
      const supabase=getSupabaseBrowserClient();
      const {data,error:signInError}=await supabase.auth.signInWithPassword({email:email.trim(),password});
      if(signInError)throw signInError;
      const accessToken=data.session?.access_token;
      if(!accessToken)throw new Error('A secure session could not be created. Please try again.');
      const response=await fetch(`${process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000'}/auth/supabase/me`,{headers:{Authorization:`Bearer ${accessToken}`}});
      const profile=await response.json();
      if(!response.ok)throw new Error(profile.detail||'This account is not activated for administrator access.');
      if(!profile.is_admin)throw new Error('This account is not authorised for the Vortex control centre.');
      router.push('/dashboard');
    }catch(err){setError(err.message);}finally{setLoading(false);}
  }
  return <main className="admin-auth">
    <section className="admin-visual">
      <div className="admin-brand"><span className="admin-mark">V</span><span>VORTEX TECHNOLOGIES</span></div>
      <div className="admin-visual-copy"><span>CHIKORO DIGITAL · CONTROL CENTRE</span><h1>Every school. One clear view.</h1><p>Manage schools, support teams and keep your education operations moving with confidence.</p></div>
      <div className="admin-visual-foot">Secure administration workspace · Chikoro Digital</div>
    </section>
    <section className="admin-panel"><div className="admin-card">
      <div className="admin-eyebrow">Administrator portal</div><h2>Welcome back</h2><p className="intro">Sign in with your administrator credentials to access the control centre.</p>
      {error&&<div className="admin-alert error" role="alert">{error}</div>}
      <form onSubmit={submit}>
        <div className="admin-field"><label htmlFor="admin-email">Email address</label><input id="admin-email" type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} placeholder="name@organisation.com" required /></div>
        <div className="admin-field"><label htmlFor="admin-password">Password</label><input id="admin-password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Enter your password" required /></div>
        <button className="admin-button" type="submit" disabled={loading}>{loading?'Signing in…':'Sign in securely'}</button>
      </form>
      <div className="admin-links"><span>New administrator? <a href="/register">Set up account</a></span><a href="https://chikoro-digital.vercel.app">Student & parent portal</a></div>
      <p className="admin-note">Access is restricted to authorised school and platform administrators. Never share your password or verification codes.</p>
    </div></section>
  </main>;
}