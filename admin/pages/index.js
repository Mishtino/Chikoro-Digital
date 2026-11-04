import { useState } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseBrowserClient } from '../lib/supabase';
export default function AdminLogin() {
  const router=useRouter(); const [email,setEmail]=useState(''); const [password,setPassword]=useState(''); const [error,setError]=useState(''); const [notice,setNotice]=useState(''); const [loading,setLoading]=useState(false); const [resending,setResending]=useState(false);
  async function resendVerification(){
    const address=email.trim();
    if(!address){setError('Enter your Vortex account email address first.');return;}
    setError('');setNotice('');setResending(true);
    try{
      const {error:resendError}=await getSupabaseBrowserClient().auth.resend({type:'signup',email:address});
      if(resendError)throw resendError;
      setNotice('If this address has a pending signup, a fresh verification email has been sent. Check your inbox and spam folder.');
    }catch(err){setError(err.message||'Unable to resend verification email.');}
    finally{setResending(false);}
  }
  async function submit(e){
    e.preventDefault();setError('');setNotice('');setLoading(true);
    try{
      const supabase=getSupabaseBrowserClient();
      const {data,error:signInError}=await supabase.auth.signInWithPassword({email:email.trim(),password});
      if(signInError)throw signInError;
      const accessToken=data.session?.access_token;
      if(!accessToken)throw new Error('A secure session could not be created. Please try again.');
      const response=await fetch(`${process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000'}/auth/supabase/me`,{headers:{Authorization:`Bearer ${accessToken}`}});
      const profile=await response.json();
      if(!response.ok){await supabase.auth.signOut();throw new Error(profile.detail||'This account is not activated for Vortex platform access.');}
      if(!profile.is_platform_staff){await supabase.auth.signOut();throw new Error('This account is not authorised for the Vortex Developer Portal.');}
      router.push('/dashboard');
    }catch(err){setError(err.message);}finally{setLoading(false);}
  }
  return <main className="admin-auth">
    <section className="admin-visual">
      <div className="admin-brand"><span className="admin-mark">V</span><span>VORTEX TECHNOLOGIES</span></div>
      <div className="admin-visual-copy"><span>VORTEX TECHNOLOGIES · DEVELOPER PORTAL</span><h1>Every school. One clear view.</h1><p>Operate the Chikoro Digital platform, manage school tenants and monitor the systems behind every school.</p></div>
      <div className="admin-visual-foot">Secure administration workspace · Chikoro Digital</div>
    </section>
    <section className="admin-panel"><div className="admin-card">
      <div className="admin-eyebrow">Vortex developer portal</div><h2>Welcome back</h2><p className="intro">Sign in with your authorised Vortex platform credentials.</p>
      {error&&<div className="admin-alert error" role="alert">{error}</div>}
      {notice&&<div className="admin-alert success" role="status">{notice}</div>}
      <form onSubmit={submit}>
        <div className="admin-field"><label htmlFor="admin-email">Email address</label><input id="admin-email" type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} placeholder="name@organisation.com" required /></div>
        <div className="admin-field"><label htmlFor="admin-password">Password</label><input id="admin-password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Enter your password" required /></div>
        <button className="admin-button" type="submit" disabled={loading}>{loading?'Signing in…':'Sign in securely'}</button>
        <button className="admin-resend" type="button" onClick={resendVerification} disabled={resending}>{resending?'Sending…':'Resend verification email'}</button>
      </form>
      <div className="admin-links"><span>Platform access is provisioned securely</span><a href="https://chikoro-digital.vercel.app">Student & parent portal</a></div>
      <p className="admin-note">Access is restricted to explicitly provisioned Vortex platform staff. Your role determines which areas you can access. Never share your password or verification codes.</p>
    </div></section>
  </main>;
}