export default function PortalRegister() {
  return (
    <main className="auth-shell">
      <section className="auth-visual">
        <div className="brand-lockup"><span className="brand-mark">C</span><span>CHIKORO DIGITAL</span></div>
        <div className="visual-copy"><span className="eyebrow">Secure account activation</span><h1>Your school journey, all in one place.</h1><p>Your school verifies each student and parent account before portal access is enabled.</p></div>
        <div className="visual-foot">Simple. Secure. Connected.</div>
      </section>
      <section className="auth-panel"><div className="auth-card">
        <div className="form-eyebrow">Student & parent onboarding</div><h2>Activate your account</h2>
        <p className="auth-subtitle">Self-service activation is temporarily paused while we move account creation to Supabase Auth. This prevents duplicate identities and unverified links to student records.</p>
        <div className="auth-alert" role="status">Please contact your school office and request a verified Chikoro Digital activation invitation. Parents must have their guardian relationship verified by the school.</div>
        <div className="auth-links"><a href="/portal/login">Return to sign in</a></div>
        <p className="auth-note">Never share a school-issued one-time PIN with anyone claiming to be technical support.</p>
      </div></section>
    </main>
  );
}
