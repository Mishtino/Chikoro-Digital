export default function AdminRegister() {
  return <main className="admin-auth">
    <section className="admin-visual">
      <div className="admin-brand"><span className="admin-mark">V</span><span>VORTEX TECHNOLOGIES</span></div>
      <div className="admin-visual-copy"><span>CHIKORO DIGITAL · ACCOUNT SECURITY</span><h1>Vortex platform access is invitation-only.</h1><p>Developer identities are provisioned and verified through the Vortex platform-owner process.</p></div>
      <div className="admin-visual-foot">Secure administration workspace · Chikoro Digital</div>
    </section>
    <section className="admin-panel"><div className="admin-card">
      <div className="admin-eyebrow">Restricted onboarding</div><h2>Registration is closed</h2>
      <p className="intro">For security, administrator accounts cannot be self-registered from a public page. Only an authorised Vortex platform owner can provision a developer identity for a verified email address.</p>
      <div className="admin-links"><a href="/">Return to sign in</a><a href="https://chikoro-digital.vercel.app">Student & parent portal</a></div>
      <p className="admin-note">Creating a sign-in identity does not grant platform permissions. Vortex access is activated separately after identity and account ownership checks.</p>
    </div></section>
  </main>;
}
