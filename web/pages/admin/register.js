export default function AdminRegistrationUnavailable() {
  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div className="auth-card">
          <div className="form-eyebrow">Chikoro Digital · School administration</div>
          <h1>Administrator access is invitation-only</h1>
          <p className="auth-subtitle">
            School administrator accounts are provisioned through the Chikoro Digital
            platform onboarding process. Contact your school’s authorised platform
            administrator to request access.
          </p>
          <p className="auth-note">
            Vortex Technologies platform operator access is separate from school
            administrator access. This page cannot register or grant either role.
          </p>
          <div className="auth-links">
            <a href="/portal/login">Return to sign in</a>
          </div>
        </div>
      </section>
    </main>
  );
}
