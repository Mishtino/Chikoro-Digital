import { useState } from 'react';
import { createClient } from '@supabase/supabase-js';

const ADMIN_EMAIL='msirewu56@gmail.com';
function supabaseClient(){
  const url=process.env.NEXT_PUBLIC_SUPABASE_URL;const key=process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if(!url||!key)throw new Error('Registration is temporarily unavailable. Please contact support.');
  return createClient(url,key,{auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:true}});
}
export default function AdminRegister(){
  const [password,setPassword]=useState('');const [confirm,setConfirm]=useState('');const [error,setError]=useState('');const [message,setMessage]=useState('');const [loading,setLoading]=useState(false);
  async function submit(e){
    e.preventDefault();setError('');setMessage('');
    if(password.length<12)return setError('Choose a password with at least 12 characters.');
    if(password!==confirm)return setError('The passwords do not match.');
    setLoading(true);
    try{
      const {data,error:signupError}=await supabaseClient().auth.signUp({email:ADMIN_EMAIL,password,options:{emailRedirectTo:window.location.origin+'/register?verified=1'}});
      if(signupError)throw signupError;
      setMessage(data.session?'Your sign-in identity has been created. Check your email for any confirmation request. Administrator access is activated separately after verification.':'Registration started. Check msirewu56@gmail.com and open the confirmation link. Your administrator access will be activated only after identity verification.');
      setPassword('');setConfirm('');
    }catch(err){setError(err.message||'Unable to create the account. If you already registered, check your email.');}
    finally{setLoading(false);}
  }
  return <main className="admin-auth">
    <section className="admin-visual">
      <div className="admin-brand"><span className="admin-mark">V</span><span>VORTEX TECHNOLOGIES</span></div>
      <div className="admin-visual-copy"><span>CHIKORO DIGITAL · ACCOUNT SECURITY</span><h1>A secure start to smarter school management.</h1><p>Create your administrator sign-in identity. Your platform access is verified separately before any privileged permissions are enabled.</p></div>
      <div className="admin-visual-foot">Secure administration workspace · Chikoro Digital</div>
    </section>
    <section className="admin-panel"><div className="admin-card">
      <div className="admin-eyebrow">Administrator onboarding</div><h2>Create your account</h2><p className="intro">Set a private password for the designated platform administrator account.</p>
      {error&&<div className="admin-alert error" role="alert">{error}</div>}{message&&<div className="admin-alert success" role="status">{message}</div>}
      <form onSubmit={submit}>
        <div className="admin-field"><label htmlFor="admin-register-email">Administrator email</label><input id="admin-register-email" type="email" value={ADMIN_EMAIL} readOnly /></div>
        <div className="admin-field"><label htmlFor="new-password">Create password</label><input id="new-password" type="password" autoComplete="new-password" minLength={12} required value={password} onChange={e=>setPassword(e.target.value)} placeholder="At least 12 characters" /></div>
        <div className="admin-field"><label htmlFor="confirm-password">Confirm password</label><input id="confirm-password" type="password" autoComplete="new-password" minLength={12} required value={confirm} onChange={e=>setConfirm(e.target.value)} placeholder="Enter the password again" /></div>
        <button className="admin-button" type="submit" disabled={loading}>{loading?'Creating account…':'Create secure sign-in'}</button>
      </form>
      <div className="admin-links"><span>Already registered? <a href="/">Sign in</a></span></div>
      <p className="admin-note">This step creates a Supabase sign-in identity only. It does not grant administrator permissions. Those are enabled after email verification and secure account linking.</p>
    </div></section>
  </main>;
}